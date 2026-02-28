"""Catalog scraper -- extracts ALL products from Tiendeo, including non-promotional.

Unlike the regular TiendeoScraper which only saves products that have a price
(i.e. active offers), this scraper also creates Product rows for items without
a discounted price.  This populates the full catalog so users can build a
watchlist from all available products, not just those currently on sale.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from app.database import async_session
from app.scrapers.tiendeo import TiendeoScraper, TIENDEO_CHAINS, _HEADERS, _COOKIES
from app.services.product_matcher import ProductMatcher

logger = logging.getLogger(__name__)


class CatalogScraper:
    """Scrapes Tiendeo catalogs and saves ALL products, even without offers."""

    def __init__(self, chain_slug: str, *, store_id: uuid.UUID | None = None) -> None:
        self.chain_slug = chain_slug
        self.store_id = store_id
        self._tiendeo = TiendeoScraper(chain_slug, store_id=store_id)
        self._matcher = ProductMatcher()

    async def scrape(self) -> int:
        """Scrape all catalogs and return count of products processed."""
        tiendeo_slug = TIENDEO_CHAINS.get(self.chain_slug)
        if not tiendeo_slug:
            logger.error("Chain '%s' not supported for catalog sync.", self.chain_slug)
            return 0

        total = 0
        try:
            client = await self._tiendeo._get_http_client()

            catalogs = await self._tiendeo._discover_catalogs(client, tiendeo_slug)
            if not catalogs:
                logger.warning(
                    "No catalogs found for '%s' during catalog sync.",
                    self.chain_slug,
                )
                return 0

            logger.info(
                "Catalog sync: found %d catalog(s) for '%s'.",
                len(catalogs),
                self.chain_slug,
            )

            for catalog in catalogs:
                try:
                    count = await self._process_catalog_products(client, catalog)
                    total += count
                except Exception:
                    logger.exception(
                        "Error processing catalog %s for '%s' during catalog sync.",
                        catalog.get("id"),
                        self.chain_slug,
                    )
                await asyncio.sleep(2)

        except Exception:
            logger.exception("Catalog sync failed for '%s'.", self.chain_slug)
        finally:
            await self._tiendeo.close()

        logger.info(
            "Catalog sync complete for '%s': %d products processed.",
            self.chain_slug,
            total,
        )
        return total

    async def _process_catalog_products(
        self, client, catalog: dict[str, Any]
    ) -> int:
        """Fetch a catalog page and save ALL products (even without price)."""
        from bs4 import BeautifulSoup

        cat_id = catalog["id"]
        url = f"{self._tiendeo.base_url}/Cataloghi/{cat_id}"
        logger.info("Catalog sync: fetching %s", url)

        resp = await client.get(url, headers=_HEADERS, cookies=_COOKIES)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        next_data = self._tiendeo._parse_next_data(soup)
        if not next_data:
            return 0

        api_res = (
            next_data.get("props", {})
            .get("pageProps", {})
            .get("apiResources", {})
        )
        gibs = api_res.get("flyerGibsData", {}).get("flyerGibs", [])
        if not gibs:
            return 0

        saved = 0
        seen: set[str] = set()

        async with async_session() as session:
            for gib in gibs:
                raw_name = (gib.get("title") or "").strip()
                if not raw_name or len(raw_name) < 2:
                    continue

                settings = gib.get("settings") or {}

                # Brand
                brand_from_settings = (settings.get("brand") or "").strip() or None
                brand_from_name, product_name = self._matcher.extract_brand_from_name(
                    raw_name
                )
                brand = brand_from_settings or brand_from_name

                image_url = (settings.get("image_url") or "").strip() or None

                # Dedup within this catalog
                dedup_key = product_name.lower()
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)

                try:
                    await self._matcher.create_or_match_product(
                        {
                            "name": product_name,
                            "brand": brand,
                            "category": None,
                            "image_url": image_url,
                            "source": "tiendeo",
                        },
                        session=session,
                    )
                    saved += 1
                except Exception:
                    logger.exception(
                        "Failed to save catalog product: %s", product_name
                    )

        logger.info(
            "Catalog sync: processed %d products from catalog %s.",
            saved,
            cat_id,
        )
        return saved
