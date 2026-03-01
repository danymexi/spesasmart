"""Iperal Spesa Online catalog scraper.

Calls the public REST API at iperalspesaonline.it/ebsn/api/ to fetch
the complete product catalog across all categories.  No authentication
is required — the API serves product data to anonymous users.

API endpoints used:
    GET /ebsn/api/category?filtered=true          → all categories + subcategories
    GET /ebsn/api/products?parent_category_id={id}&page_size={n}&page={p}  → products
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import httpx

from app.database import async_session
from app.services.product_matcher import ProductMatcher

logger = logging.getLogger(__name__)

BASE_URL = "https://www.iperalspesaonline.it/ebsn/api"
PAGE_SIZE = 50
REQUEST_DELAY = 1.0  # seconds between API calls to be polite

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "it-IT,it;q=0.9",
}


class IperalOnlineScraper:
    """Scrapes the full Iperal Spesa Online product catalog via REST API."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._matcher = ProductMatcher()
        self._category_names: dict[int, str] = {}

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                follow_redirects=True,
                headers=_HEADERS,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def scrape(self) -> int:
        """Scrape all products from Iperal Spesa Online.

        Returns the total number of products processed.
        """
        total = 0
        try:
            categories = await self._fetch_categories()
            if not categories:
                logger.warning("No categories found from Iperal Online API.")
                return 0

            logger.info(
                "Iperal Online: found %d leaf categories to scrape.",
                len(categories),
            )

            for cat_id, cat_name, parent_name in categories:
                try:
                    count = await self._scrape_category(cat_id, cat_name, parent_name)
                    total += count
                    logger.info(
                        "Iperal Online: %d products from '%s > %s'.",
                        count, parent_name, cat_name,
                    )
                except Exception:
                    logger.exception(
                        "Error scraping Iperal category %d ('%s').",
                        cat_id, cat_name,
                    )
                await asyncio.sleep(REQUEST_DELAY)

        except Exception:
            logger.exception("Iperal Online catalog scrape failed.")
        finally:
            await self.close()

        logger.info("Iperal Online catalog scrape complete: %d products.", total)
        return total

    # ------------------------------------------------------------------
    # Category fetching
    # ------------------------------------------------------------------

    async def _fetch_categories(self) -> list[tuple[int, str, str]]:
        """Fetch all categories and return leaf (sub)categories.

        Returns list of (categoryId, subcategoryName, parentCategoryName).
        """
        client = await self._get_client()
        resp = await client.get(
            f"{BASE_URL}/category", params={"filtered": "true", "hash": "w0d0t0"}
        )
        resp.raise_for_status()
        data = resp.json()

        top_categories = data.get("data", {}).get("categories", [])
        leaves: list[tuple[int, str, str]] = []

        for top in top_categories:
            parent_name = top.get("name", "")
            self._category_names[top["categoryId"]] = parent_name

            subcats = top.get("categories", [])
            if subcats:
                for sub in subcats:
                    sub_name = sub.get("name", "")
                    sub_id = sub["categoryId"]
                    self._category_names[sub_id] = sub_name
                    leaves.append((sub_id, sub_name, parent_name))
            else:
                # No subcategories — the top category is itself a leaf
                leaves.append((top["categoryId"], parent_name, parent_name))

        return leaves

    # ------------------------------------------------------------------
    # Product scraping per category
    # ------------------------------------------------------------------

    async def _scrape_category(
        self, category_id: int, category_name: str, parent_name: str
    ) -> int:
        """Paginate through all products in a category and save them."""
        client = await self._get_client()
        saved = 0
        page = 1

        while True:
            resp = await client.get(
                f"{BASE_URL}/products",
                params={
                    "parent_category_id": category_id,
                    "page_size": PAGE_SIZE,
                    "page": page,
                    "hash": "w0d0t0",
                },
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})

            products = data.get("products", [])
            page_info = data.get("page", {})

            if not products:
                break

            async with async_session() as session:
                for prod in products:
                    try:
                        count = await self._save_product(
                            prod, category_name, parent_name, session
                        )
                        saved += count
                    except Exception:
                        logger.exception(
                            "Failed to save Iperal product: %s",
                            prod.get("name"),
                        )

            tot_pages = page_info.get("totPages", 1)
            if page >= tot_pages:
                break

            page += 1
            await asyncio.sleep(REQUEST_DELAY)

        return saved

    # ------------------------------------------------------------------
    # Product persistence
    # ------------------------------------------------------------------

    async def _save_product(
        self,
        prod: dict[str, Any],
        category_name: str,
        parent_name: str,
        session,
    ) -> int:
        """Save a single product via ProductMatcher. Returns 1 on success, 0 on skip."""
        name = (prod.get("name") or "").strip()
        if not name or len(name) < 2:
            return 0

        # Brand from vendor
        vendor = prod.get("vendor") or {}
        brand = (vendor.get("name") or "").strip() or None

        # Also check shortDescr which sometimes has the brand
        short_descr = (prod.get("shortDescr") or "").strip()
        if not brand and short_descr:
            brand = short_descr

        # Barcode (EAN)
        barcode = (prod.get("barcode") or "").strip() or None

        # Image URL
        image_url = (prod.get("mediaURLMedium") or prod.get("mediaURL") or "").strip() or None

        # Unit — extract weight/quantity from description (e.g. "g 150", "ml 500")
        # The description field can be long; we only want the short unit part.
        raw_desc = (prod.get("description") or "").strip()
        unit = self._extract_unit(raw_desc, prod.get("productInfos"))

        # Use parent category name as the category for our DB
        # (e.g. "Frutta e verdura" rather than the subcategory "Frutta")
        category = parent_name or category_name

        # Truncate unit to fit DB column (VARCHAR 50)
        if unit and len(unit) > 50:
            unit = unit[:47] + "..."

        await self._matcher.create_or_match_product(
            {
                "name": name,
                "brand": brand,
                "category": category,
                "subcategory": category_name if category_name != parent_name else None,
                "unit": unit,
                "barcode": barcode,
                "image_url": image_url,
                "source": "iperal_online",
            },
            session=session,
        )
        return 1

    @staticmethod
    def _extract_unit(description: str, product_infos: dict | None = None) -> str | None:
        """Extract a short unit string from the Iperal description.

        The API description can contain full text like:
            "g 500, Pasta biologica di semola di grano khorasan KAMUT"
        We want just "g 500" or "500 g".

        Also checks productInfos for WEIGHT_SELLING / WEIGHT_UNIT_SELLING.
        """
        if not description:
            return None

        # Try productInfos first (structured data)
        if product_infos:
            weight = (product_infos.get("WEIGHT_SELLING") or "").strip()
            weight_unit = (product_infos.get("WEIGHT_UNIT_SELLING") or "").strip()
            if weight and weight != "0" and weight_unit:
                return f"{weight} {weight_unit}"

        # Parse from description: take the first comma-separated segment
        # that looks like a quantity
        first_part = description.split(",")[0].strip()

        # Match patterns like "g 500", "ml 750", "kg 1", "l 1.5", "pz 6"
        qty_pattern = re.match(
            r"^(g|kg|ml|cl|l|pz|conf|capsule)\s+\d+(?:[.,]\d+)?",
            first_part,
            re.IGNORECASE,
        )
        if qty_pattern:
            return qty_pattern.group(0).strip()

        # Match "500 g", "1,5 kg" etc.
        qty_pattern2 = re.match(
            r"^\d+(?:[.,]\d+)?\s*(g|kg|ml|cl|l|pz|conf|capsule)\b",
            first_part,
            re.IGNORECASE,
        )
        if qty_pattern2:
            return qty_pattern2.group(0).strip()

        # Match "Confezione da circa 1 kg (5 pz circa)"
        confezione = re.search(
            r"(\d+(?:[.,]\d+)?\s*(?:g|kg|ml|cl|l|pz))",
            first_part,
            re.IGNORECASE,
        )
        if confezione:
            return confezione.group(1).strip()

        # Fallback: if the first part is short enough, use it as-is
        if len(first_part) <= 50:
            return first_part or None

        return None
