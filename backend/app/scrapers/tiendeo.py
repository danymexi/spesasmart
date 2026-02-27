"""Tiendeo.it aggregator scraper -- HTTP-only, no Playwright needed.

Tiendeo is an international flyer aggregator built on Next.js SSR.
Product data is embedded in the ``__NEXT_DATA__`` JSON blob:

- Landing page (``/Volantini/{chain}``):
    ``apiResources.flyersByRetailer`` — list of active catalog objects.
- Catalog page (``/Cataloghi/{id}``):
    ``apiResources.flyerGibsData.flyerGibs`` — all products with price,
    brand, image, and category ID.

No Playwright needed — plain httpx + BeautifulSoup.

Supported chains: esselunga, lidl, coop, iperal.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from bs4 import BeautifulSoup

from app.database import async_session
from app.models.chain import Chain
from app.models.flyer import Flyer
from app.models.offer import Offer
from app.scrapers.base import BaseScraper
from app.services.product_matcher import ProductMatcher

logger = logging.getLogger(__name__)

# Map our chain slugs to Tiendeo URL slugs
TIENDEO_CHAINS: dict[str, str] = {
    "esselunga": "esselunga",
    "lidl": "lidl",
    "coop": "coop",
    "iperal": "iperal",
}

# Headers that mimic an Italian browser
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Tiendeo geolocation cookie for Monza area
_COOKIES = {
    "tiendeo_geolocation": "lat=45.5845&lng=9.2744&city=Monza&region=Lombardia&country=IT",
}


class TiendeoScraper(BaseScraper):
    """HTTP-only scraper that pulls offers from tiendeo.it for a given chain."""

    name = "Tiendeo"
    slug = "tiendeo"
    base_url = "https://www.tiendeo.it"

    def __init__(self, chain_slug: str, *, store_id: uuid.UUID | None = None) -> None:
        self.chain_slug = chain_slug
        self.chain_name = chain_slug.title()
        self.store_id = store_id
        self.name = self.chain_name
        self.slug = chain_slug
        super().__init__()
        self._matcher = ProductMatcher()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def scrape(self) -> list[dict[str, Any]]:
        """Scrape all active catalogs for the configured chain from Tiendeo."""
        tiendeo_slug = TIENDEO_CHAINS.get(self.chain_slug)
        if not tiendeo_slug:
            logger.error("Chain '%s' not supported on Tiendeo.", self.chain_slug)
            return []

        flyers_data: list[dict[str, Any]] = []

        try:
            client = await self._get_http_client()

            # Step 1: Discover active catalog IDs
            catalogs = await self._discover_catalogs(client, tiendeo_slug)
            if not catalogs:
                logger.warning("No catalogs found for '%s' on Tiendeo.", self.chain_slug)
                return []

            logger.info(
                "Found %d catalog(s) for '%s' on Tiendeo.",
                len(catalogs),
                self.chain_slug,
            )

            # Step 2: Fetch products from each catalog
            for catalog in catalogs:
                try:
                    flyer_data = await self._process_catalog(client, catalog)
                    if flyer_data:
                        flyers_data.append(flyer_data)
                except Exception:
                    logger.exception(
                        "Error processing Tiendeo catalog %s for '%s'.",
                        catalog.get("id"),
                        self.chain_slug,
                    )

                # Polite delay between catalog fetches
                await asyncio.sleep(2)

        except Exception:
            logger.exception("Tiendeo scraping failed for '%s'.", self.chain_slug)
        finally:
            await self.close()

        total = sum(len(f.get("products", [])) for f in flyers_data)
        logger.info(
            "Tiendeo scraping complete for '%s': %d catalog(s), %d total products.",
            self.chain_slug,
            len(flyers_data),
            total,
        )
        return flyers_data

    # ------------------------------------------------------------------
    # Catalog discovery from /Volantini/{chain}
    # ------------------------------------------------------------------

    async def _discover_catalogs(
        self, client, tiendeo_slug: str
    ) -> list[dict[str, Any]]:
        """Fetch the chain's landing page and extract catalog IDs + metadata.

        Primary source: ``apiResources.flyersByRetailer`` in ``__NEXT_DATA__``.
        Fallback: ``apiResources.mainFlyer``.
        """
        url = f"{self.base_url}/Volantini/{tiendeo_slug}"
        logger.info("Fetching Tiendeo landing page: %s", url)

        resp = await client.get(url, headers=_HEADERS, cookies=_COOKIES)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        catalogs: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        next_data = self._parse_next_data(soup)
        if not next_data:
            logger.warning("No __NEXT_DATA__ found on Tiendeo landing page.")
            return []

        api_res = (
            next_data.get("props", {})
            .get("pageProps", {})
            .get("apiResources", {})
        )

        # Primary: flyersByRetailer — list of all active catalogs for this chain
        for flyer_obj in api_res.get("flyersByRetailer", []):
            cat = self._catalog_from_flyer_obj(flyer_obj)
            if cat and cat["id"] not in seen_ids:
                seen_ids.add(cat["id"])
                catalogs.append(cat)

        # Fallback: mainFlyer (single highlighted catalog)
        if not catalogs:
            main = api_res.get("mainFlyer")
            if main:
                cat = self._catalog_from_flyer_obj(main)
                if cat and cat["id"] not in seen_ids:
                    seen_ids.add(cat["id"])
                    catalogs.append(cat)

        return catalogs

    # ------------------------------------------------------------------
    # Catalog processing: fetch page and extract products from flyerGibs
    # ------------------------------------------------------------------

    async def _process_catalog(
        self, client, catalog: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Fetch a catalog page and extract products from flyerGibsData."""
        cat_id = catalog["id"]
        url = f"{self.base_url}/Cataloghi/{cat_id}"
        logger.info("Fetching Tiendeo catalog %s: %s", cat_id, url)

        resp = await client.get(url, headers=_HEADERS, cookies=_COOKIES)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Extract products from __NEXT_DATA__ → apiResources.flyerGibsData
        products = self._extract_products_from_gibs(soup)

        if not products:
            logger.info("No products found in catalog %s.", cat_id)
            return None

        logger.info(
            "Extracted %d products from Tiendeo catalog %s ('%s').",
            len(products),
            cat_id,
            catalog.get("title", ""),
        )

        valid_from = catalog.get("valid_from") or date.today()
        valid_to = catalog.get("valid_to") or date.today()

        flyer_data = {
            "chain": self.chain_name,
            "slug": self.chain_slug,
            "title": catalog.get("title", f"Tiendeo {self.chain_name}"),
            "source_url": url,
            "valid_from": valid_from,
            "valid_to": valid_to,
            "products": products,
            "image_paths": [],
            "store_id": self.store_id,
        }

        await self._persist_offers(flyer_data)
        return flyer_data

    # ------------------------------------------------------------------
    # Product extraction from __NEXT_DATA__ flyerGibs
    # ------------------------------------------------------------------

    def _extract_products_from_gibs(
        self, soup: BeautifulSoup
    ) -> list[dict[str, Any]]:
        """Parse products from ``apiResources.flyerGibsData.flyerGibs``."""
        next_data = self._parse_next_data(soup)
        if not next_data:
            return []

        api_res = (
            next_data.get("props", {})
            .get("pageProps", {})
            .get("apiResources", {})
        )
        gibs_data = api_res.get("flyerGibsData", {})
        gibs = gibs_data.get("flyerGibs", [])

        if not gibs:
            return []

        products: list[dict[str, Any]] = []
        seen: set[str] = set()

        for gib in gibs:
            raw_name = (gib.get("title") or "").strip()
            if not raw_name or len(raw_name) < 2:
                continue

            settings = gib.get("settings") or {}

            # Extract price
            price_ext = settings.get("price_extended") or {}
            raw_price = price_ext.get("digits") or ""
            if not raw_price:
                # Fallback: parse from settings.price ("€ 1.47")
                raw_price = (settings.get("price") or "").strip()

            price = self.normalize_price(raw_price)
            if price is None:
                continue

            # Extract original price (before discount)
            original_price = None
            starting = settings.get("starting_price") or {}
            starting_digits = (starting.get("digits") or "").strip()
            if starting_digits:
                original_price = self.normalize_price(starting_digits)

            # Extract discount percentage from sale field ("−30%", etc.)
            discount_pct_str = (settings.get("sale") or "").strip() or None

            # Brand — either from settings.brand or split from name
            brand_from_settings = (settings.get("brand") or "").strip() or None
            brand_from_name, product_name = self._matcher.extract_brand_from_name(raw_name)
            brand = brand_from_settings or brand_from_name

            # Image URL
            image_url = (settings.get("image_url") or "").strip() or None

            # Dedup within this catalog
            dedup_key = f"{product_name.lower()}|{price}"
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            products.append({
                "name": product_name,
                "brand": brand,
                "category": None,
                "original_price": str(original_price) if original_price else None,
                "offer_price": str(price),
                "discount_pct": discount_pct_str,
                "discount_type": "percentage" if discount_pct_str else None,
                "quantity": None,
                "price_per_unit": None,
                "raw_text": raw_name,
                "confidence": 0.95,
                "image_url": image_url,
            })

        return products

    # ------------------------------------------------------------------
    # Database persistence
    # ------------------------------------------------------------------

    async def _persist_offers(self, flyer_data: dict[str, Any]) -> None:
        """Create a Flyer row and persist products+offers using ProductMatcher."""
        from sqlalchemy import and_, select

        store_id = flyer_data.get("store_id") or self.store_id
        valid_from = flyer_data.get("valid_from") or date.today()
        valid_to = flyer_data.get("valid_to") or date.today()

        async with async_session() as session:
            # Find chain
            stmt = select(Chain).where(Chain.slug == self.chain_slug)
            result = await session.execute(stmt)
            chain = result.scalar_one_or_none()
            if chain is None:
                logger.error("Chain '%s' not found in DB.", self.chain_slug)
                return

            # Date-based dedup
            stmt_existing = select(Flyer).where(
                and_(
                    Flyer.source_url == flyer_data["source_url"],
                    Flyer.chain_id == chain.id,
                    Flyer.valid_from == valid_from,
                    Flyer.valid_to == valid_to,
                )
            )
            existing = (await session.execute(stmt_existing)).scalar_one_or_none()
            if existing:
                logger.info(
                    "Tiendeo flyer already exists for '%s' (%s to %s, id=%s), skipping.",
                    self.chain_slug,
                    valid_from,
                    valid_to,
                    existing.id,
                )
                return

            flyer = Flyer(
                chain_id=chain.id,
                store_id=store_id,
                title=flyer_data["title"],
                valid_from=valid_from,
                valid_to=valid_to,
                source_url=flyer_data["source_url"],
                pages_count=1,
                status="processing",
            )
            session.add(flyer)
            await session.commit()
            await session.refresh(flyer)
            flyer_id = flyer.id
            chain_id = chain.id

        # Save products using ProductMatcher for fuzzy dedup
        saved = 0
        async with async_session() as session:
            for prod_data in flyer_data.get("products", []):
                try:
                    name = (prod_data.get("name") or "").strip()
                    if not name:
                        continue

                    offer_price = self.normalize_price(prod_data.get("offer_price"))
                    if offer_price is None:
                        continue

                    # Use ProductMatcher for fuzzy find-or-create
                    product = await self._find_or_create_product(
                        {
                            "name": name,
                            "brand": prod_data.get("brand"),
                            "category": prod_data.get("category"),
                            "image_url": prod_data.get("image_url"),
                        },
                        session=session,
                    )

                    original_price = self.normalize_price(
                        prod_data.get("original_price")
                    )
                    discount_pct = self.normalize_discount_pct(
                        prod_data.get("discount_pct")
                    )

                    offer = Offer(
                        product_id=product.id,
                        flyer_id=flyer_id,
                        chain_id=chain_id,
                        store_id=store_id,
                        original_price=original_price,
                        offer_price=offer_price,
                        discount_pct=discount_pct,
                        discount_type=prod_data.get("discount_type"),
                        quantity=prod_data.get("quantity"),
                        price_per_unit=None,
                        valid_from=valid_from,
                        valid_to=valid_to,
                        raw_text=prod_data.get("raw_text", "")[:500],
                        confidence=Decimal(str(prod_data.get("confidence", 0.95))),
                    )
                    session.add(offer)
                    saved += 1

                except Exception:
                    logger.exception(
                        "Failed to save Tiendeo product: %s", prod_data.get("name")
                    )

            flyer = await session.get(Flyer, flyer_id)
            if flyer:
                flyer.status = "processed"
            await session.commit()

        logger.info(
            "Tiendeo: persisted %d products for '%s' (flyer %s).",
            saved,
            self.chain_slug,
            flyer_id,
        )

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_next_data(soup: BeautifulSoup) -> dict | None:
        """Extract and parse the ``__NEXT_DATA__`` JSON blob."""
        tag = soup.find("script", id="__NEXT_DATA__")
        if not tag or not tag.string:
            return None
        try:
            return json.loads(tag.string)
        except (json.JSONDecodeError, TypeError):
            return None

    @staticmethod
    def _catalog_from_flyer_obj(flyer_obj: dict) -> dict[str, Any] | None:
        """Build a catalog dict from a Tiendeo flyer object.

        Works for both ``flyersByRetailer`` entries and ``mainFlyer``.
        """
        cat_id = str(flyer_obj.get("id", ""))
        if not cat_id:
            return None

        valid_from = _parse_iso_date(flyer_obj.get("start_date"))
        valid_to = _parse_iso_date(flyer_obj.get("end_date"))

        return {
            "id": cat_id,
            "title": (flyer_obj.get("title") or f"Catalogo {cat_id}")[:200],
            "valid_from": valid_from,
            "valid_to": valid_to,
        }


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _parse_iso_date(raw: str | None) -> date | None:
    """Parse an ISO-8601 date string to ``date``, returning None on failure."""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        return None
