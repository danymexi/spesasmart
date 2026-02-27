"""Tiendeo.it aggregator scraper -- HTTP-only, no Playwright needed.

Tiendeo is an international flyer aggregator that serves structured data via
Next.js SSR.  Product information is embedded in ``<script type="application/ld+json">``
tags using schema.org ``Product`` + ``Offer`` markup.

Supported chains: esselunga, lidl, coop, iperal.

Workflow per chain:
    1. GET ``/Volantini/{chain}`` to discover active catalog IDs.
    2. For each catalog, GET ``/Cataloghi/{id}`` and parse ``ld+json`` Product tags.
    3. Split brand from product name (``"Brand - Product"`` pattern).
    4. Persist via ``ProductMatcher`` for fuzzy dedup.
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

# Headers that mimic an Italian browser + Monza geolocation cookie
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
        """Fetch the chain's landing page and extract catalog IDs + metadata."""
        url = f"{self.base_url}/Volantini/{tiendeo_slug}"
        logger.info("Fetching Tiendeo landing page: %s", url)

        resp = await client.get(url, headers=_HEADERS, cookies=_COOKIES)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        catalogs: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        # Source 1: __NEXT_DATA__ → retailerHeroFlyer
        next_data = self._parse_next_data(soup)
        if next_data:
            page_props = next_data.get("props", {}).get("pageProps", {})
            hero = page_props.get("retailerHeroFlyer")
            if hero and hero.get("id"):
                cat = self._catalog_from_hero(hero)
                if cat and cat["id"] not in seen_ids:
                    seen_ids.add(cat["id"])
                    catalogs.append(cat)

        # Source 2: ld+json SaleEvent entries (list all catalogs)
        for script_tag in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script_tag.string or "")
            except (json.JSONDecodeError, TypeError):
                continue

            if isinstance(data, dict) and data.get("@type") == "OfferCatalog":
                for item in data.get("itemListElement", []):
                    cat = self._catalog_from_sale_event(item)
                    if cat and cat["id"] not in seen_ids:
                        seen_ids.add(cat["id"])
                        catalogs.append(cat)

        # Source 3: scan all href="/Cataloghi/{id}" links as fallback
        if not catalogs:
            for a_tag in soup.find_all("a", href=re.compile(r"/Cataloghi/\d+")):
                href = a_tag.get("href", "")
                match = re.search(r"/Cataloghi/(\d+)", href)
                if match:
                    cat_id = match.group(1)
                    if cat_id not in seen_ids:
                        seen_ids.add(cat_id)
                        catalogs.append({
                            "id": cat_id,
                            "title": (a_tag.get_text(strip=True) or f"Catalogo {cat_id}")[:200],
                            "valid_from": None,
                            "valid_to": None,
                        })

        return catalogs

    # ------------------------------------------------------------------
    # Catalog processing: fetch page and extract products
    # ------------------------------------------------------------------

    async def _process_catalog(
        self, client, catalog: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Fetch a single catalog page and extract all products from ld+json."""
        cat_id = catalog["id"]
        url = f"{self.base_url}/Cataloghi/{cat_id}"
        logger.info("Fetching Tiendeo catalog %s: %s", cat_id, url)

        resp = await client.get(url, headers=_HEADERS, cookies=_COOKIES)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Extract products from ld+json Product schema tags
        products = self._extract_products_from_ldjson(soup)

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
    # Product extraction from ld+json
    # ------------------------------------------------------------------

    def _extract_products_from_ldjson(
        self, soup: BeautifulSoup
    ) -> list[dict[str, Any]]:
        """Parse all ``<script type="application/ld+json">`` Product entries."""
        products: list[dict[str, Any]] = []
        seen: set[str] = set()

        for script_tag in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script_tag.string or "")
            except (json.JSONDecodeError, TypeError):
                continue

            if not isinstance(data, dict):
                continue
            if data.get("@type") != "Product":
                continue

            raw_name = (data.get("name") or "").strip()
            if not raw_name or len(raw_name) < 2:
                continue

            # Extract price from offers
            offers = data.get("offers", {})
            raw_price = offers.get("price")
            if raw_price is None:
                continue

            price = self.normalize_price(str(raw_price))
            if price is None:
                continue

            # Split brand from name: "Barilla - Penne Rigate 500g"
            brand, product_name = self._matcher.extract_brand_from_name(raw_name)

            # Dedup within this catalog
            dedup_key = f"{product_name.lower()}|{price}"
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            image_url = data.get("image")
            valid_to_str = offers.get("priceValidUntil")

            products.append({
                "name": product_name,
                "brand": brand,
                "category": None,
                "original_price": None,
                "offer_price": str(price),
                "discount_pct": None,
                "discount_type": None,
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
    def _catalog_from_hero(hero: dict) -> dict[str, Any] | None:
        """Build a catalog dict from a ``retailerHeroFlyer`` object."""
        cat_id = str(hero.get("id", ""))
        if not cat_id:
            return None

        valid_from = _parse_iso_date(hero.get("start_date"))
        valid_to = _parse_iso_date(hero.get("end_date"))

        return {
            "id": cat_id,
            "title": hero.get("title", f"Catalogo {cat_id}"),
            "valid_from": valid_from,
            "valid_to": valid_to,
        }

    @staticmethod
    def _catalog_from_sale_event(item: dict) -> dict[str, Any] | None:
        """Build a catalog dict from a schema.org SaleEvent entry."""
        url = item.get("url", "")
        match = re.search(r"/Cataloghi/(\d+)", url)
        if not match:
            return None

        cat_id = match.group(1)
        valid_from = _parse_iso_date(item.get("startDate"))
        valid_to = _parse_iso_date(item.get("endDate"))

        return {
            "id": cat_id,
            "title": (item.get("name") or f"Catalogo {cat_id}")[:200],
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
