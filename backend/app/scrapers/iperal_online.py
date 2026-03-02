"""Iperal Spesa Online catalog scraper — httpx with saved session cookies.

Uses cookies from a Playwright session file (saved by iperal_session_helper)
to make authenticated API calls via httpx.  This avoids the 403 that headless
browsers get from Iperal's bot detection.

Session bootstrap (one-time, manual):
    cd ~/spesasmart/backend
    PYTHONPATH=. python -m app.scrapers.iperal_session_helper

The session file is saved at ``backend/data/iperal_session.json`` and reused
by this scraper on every run.  If the session expires, re-run the helper.

API endpoints used (authenticated):
    GET  /ebsn/api/category?filtered=true                            → categories
    GET  /ebsn/api/products?parent_category_id={id}&page_size=50&page={p}  → products w/ prices
    GET  /ebsn/api/auth/test                                          → login check
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select

from app.database import async_session
from app.models.chain import Chain
from app.models.offer import Offer
from app.services.product_matcher import ProductMatcher

logger = logging.getLogger(__name__)

SITE_URL = "https://www.iperalspesaonline.it"
BASE_URL = f"{SITE_URL}/ebsn/api"
PAGE_SIZE = 50
REQUEST_DELAY = 1.0  # seconds between API calls

IPERAL_SESSION_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "iperal_session.json"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "it-IT,it;q=0.9",
    "Referer": f"{SITE_URL}/",
    "Origin": SITE_URL,
}

# Map Iperal weight-unit values to normalised unit references
UNIT_MAP: dict[str, str] = {
    "kg": "kg", "g": "kg", "gr": "kg",
    "l": "l", "lt": "l", "ml": "l", "cl": "l",
    "pz": "pz", "pezzi": "pz", "conf": "pz",
}


class IperalOnlineScraper:
    """Scrapes the full Iperal Spesa Online product catalog with prices."""

    def __init__(self, session_path: Path | None = None) -> None:
        self._session_path = session_path or IPERAL_SESSION_PATH
        self._matcher = ProductMatcher()
        self._category_names: dict[int, str] = {}
        self._chain_id: uuid.UUID | None = None
        self._client: httpx.AsyncClient | None = None
        self._logged_sample = False

    # ------------------------------------------------------------------
    # HTTP client with session cookies
    # ------------------------------------------------------------------

    def _load_cookies(self) -> list[dict]:
        """Load cookies from the Playwright session file."""
        if not self._session_path.exists():
            logger.warning(
                "No Iperal session file at %s. "
                "Run 'python -m app.scrapers.iperal_session_helper' first.",
                self._session_path,
            )
            return []

        try:
            state = json.loads(self._session_path.read_text())
            return state.get("cookies", [])
        except Exception:
            logger.exception("Failed to read session file.")
            return []

    async def _get_client(self) -> httpx.AsyncClient | None:
        """Build an httpx client with cookies from the saved Playwright session."""
        if self._client and not self._client.is_closed:
            return self._client

        pw_cookies = self._load_cookies()
        if not pw_cookies:
            return None

        # Convert Playwright cookies to httpx cookie jar
        cookies = httpx.Cookies()
        for c in pw_cookies:
            # Only use cookies for the iperal domain
            domain = c.get("domain", "")
            if "iperalspesaonline" not in domain:
                continue
            cookies.set(
                c["name"],
                c["value"],
                domain=domain,
                path=c.get("path", "/"),
            )

        logger.info("Loaded %d Iperal cookies from session file.", len(cookies))

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
            headers=_HEADERS,
            cookies=cookies,
        )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # API helpers
    # ------------------------------------------------------------------

    async def _api_get(self, url: str) -> dict | None:
        """GET request with session cookies, returns parsed JSON or None."""
        client = await self._get_client()
        if not client:
            return None
        try:
            resp = await client.get(url)
            if resp.status_code == 403:
                logger.error(
                    "403 Forbidden on %s — session may have expired. "
                    "Re-run iperal_session_helper.",
                    url,
                )
                return None
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.warning("HTTP %d on %s", e.response.status_code, url)
            return None
        except Exception:
            logger.exception("API call failed: %s", url)
            return None

    async def _check_auth(self) -> bool:
        """Verify the session is authenticated (userId > 0)."""
        data = await self._api_get(f"{BASE_URL}/auth/test")
        if not data:
            return False

        inner = data.get("data") or data
        user = inner.get("user") or {}
        user_id = user.get("userId", 0)
        logger.info("Iperal auth check: userId=%s", user_id)
        return bool(user_id) and int(user_id) > 0

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def scrape(self) -> int:
        """Scrape all products from Iperal Spesa Online with prices.

        Returns the total number of products processed.
        """
        total = 0
        try:
            # Initialise HTTP client
            client = await self._get_client()
            if not client:
                logger.error("Could not initialise HTTP client (no session).")
                return 0

            # Verify authentication
            if not await self._check_auth():
                logger.error(
                    "Iperal session is not authenticated. "
                    "Run 'python -m app.scrapers.iperal_session_helper' to log in."
                )
                return 0

            # Look up chain_id for "iperal"
            async with async_session() as session:
                result = await session.execute(
                    select(Chain.id).where(Chain.slug == "iperal")
                )
                row = result.scalar_one_or_none()
                if not row:
                    logger.error("Chain 'iperal' not found in DB.")
                    return 0
                self._chain_id = row
            logger.info("Iperal chain_id=%s", self._chain_id)

            # Fetch categories
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
        data = await self._api_get(f"{BASE_URL}/category?filtered=true")
        if not data:
            return []

        top_categories = (data.get("data") or data).get("categories", [])
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
                leaves.append((top["categoryId"], parent_name, parent_name))

        return leaves

    # ------------------------------------------------------------------
    # Product scraping per category
    # ------------------------------------------------------------------

    async def _scrape_category(
        self, category_id: int, category_name: str, parent_name: str
    ) -> int:
        """Paginate through all products in a category and save them."""
        saved = 0
        page = 1

        while True:
            data = await self._api_get(
                f"{BASE_URL}/products"
                f"?parent_category_id={category_id}"
                f"&page_size={PAGE_SIZE}"
                f"&page={page}"
            )
            if not data:
                break

            inner = data.get("data") or data
            products = inner.get("products", [])
            page_info = inner.get("page", {})

            if not products:
                break

            # Log the first product structure to help debug price fields
            if not self._logged_sample and products:
                sample = products[0]
                logger.info(
                    "Iperal: sample product keys=%s",
                    sorted(sample.keys()),
                )
                for key in ("price", "priceDisplay", "discountedPrice", "salePrice",
                            "grossPrice", "netPrice", "pricePerUnit",
                            "productInfos", "warehousePromo", "promo"):
                    if key in sample:
                        val = sample[key]
                        logger.info("Iperal: product.%s = %s", key, str(val)[:300])
                self._logged_sample = True

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
        """Save a single product via ProductMatcher and create/update Offer.

        Returns 1 on success, 0 on skip.
        """
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
        image_url = (
            prod.get("mediaURLMedium") or prod.get("mediaURL") or ""
        ).strip() or None

        # Unit — extract weight/quantity from description
        raw_desc = (prod.get("description") or "").strip()
        unit = self._extract_unit(raw_desc, prod.get("productInfos"))

        # Use parent category name as the category for our DB
        category = parent_name or category_name

        # Truncate unit to fit DB column (VARCHAR 50)
        if unit and len(unit) > 50:
            unit = unit[:47] + "..."

        product = await self._matcher.create_or_match_product(
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

        # Create or update Offer with price data
        if self._chain_id and product:
            await self._upsert_offer(prod, product.id, session, product_unit=unit)

        return 1

    # ------------------------------------------------------------------
    # Offer upsert (follows Esselunga pattern)
    # ------------------------------------------------------------------

    async def _upsert_offer(
        self,
        prod: dict[str, Any],
        product_id: uuid.UUID,
        session,
        product_unit: str | None = None,
    ) -> None:
        """Create or update an Offer from Iperal API price fields.

        Actual API fields (confirmed):
            price          → current selling price (already includes promos)
            priceUm        → price per unit of measure (e.g. per kg)
            priceUnitDisplay → unit label ("pz", "kg", ...)
            warehousePromo → promo details (discount, promoType, view.body)
        """
        raw_price = prod.get("price")
        if raw_price is None:
            return

        try:
            offer_price = Decimal(str(raw_price))
        except (InvalidOperation, ValueError, TypeError):
            return

        if offer_price <= 0:
            return

        # Iperal's `price` is already the final price.  The warehousePromo
        # `discount` field is an absolute amount (negative), but there is no
        # separate "original price" field in the API.  We leave original_price
        # as None since we can't reliably reconstruct it.
        original_price = None
        discount_pct = None

        # Promotion detail → discount_type (max 50 chars)
        discount_type = self._extract_discount_type(prod)

        # Price per unit
        price_per_unit = self._parse_price_per_unit(prod)

        # Unit reference from productInfos — validate with heuristic
        unit_reference = self._extract_unit_reference(prod)
        if price_per_unit and unit_reference:
            from app.services.unit_price_calculator import UnitPriceCalculator
            product_name = (prod.get("name") or "").strip()
            unit_reference = UnitPriceCalculator.infer_unit_reference(
                offer_price, price_per_unit, product_name, unit_reference,
                product_unit=product_unit,
            )

        today = date.today()
        valid_to = today + timedelta(days=7)

        # Dedup: look for existing offer for this product+chain with flyer_id IS NULL
        result = await session.execute(
            select(Offer).where(
                Offer.product_id == product_id,
                Offer.chain_id == self._chain_id,
                Offer.flyer_id.is_(None),
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.offer_price = offer_price
            existing.original_price = original_price
            existing.discount_pct = discount_pct
            existing.discount_type = discount_type
            existing.price_per_unit = price_per_unit
            existing.unit_reference = unit_reference
            existing.valid_from = today
            existing.valid_to = valid_to
        else:
            session.add(Offer(
                product_id=product_id,
                chain_id=self._chain_id,
                flyer_id=None,
                offer_price=offer_price,
                original_price=original_price,
                discount_pct=discount_pct,
                discount_type=discount_type,
                price_per_unit=price_per_unit,
                unit_reference=unit_reference,
                valid_from=today,
                valid_to=valid_to,
            ))

        await session.commit()

    # ------------------------------------------------------------------
    # Price / promo field helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_discount_type(prod: dict[str, Any]) -> str | None:
        """Extract discount/promotion label from warehousePromo.

        Actual structure:
            warehousePromo: {
                promoType: "6I01P",
                view: { body: "PI&Ugrave; BASSI SEMPRE", cssClass: "promo_piubassi" }
            }
        """
        promo = prod.get("warehousePromo")
        if not promo or not isinstance(promo, dict):
            return None

        # Try view.body first (HTML-encoded label like "PIÙ BASSI SEMPRE")
        view = promo.get("view") or {}
        body = (view.get("body") or "").strip()
        if body:
            # Decode common HTML entities
            import html as _html
            return _html.unescape(body)[:50]

        # Fallback to promoType code
        promo_type = (promo.get("promoType") or "").strip()
        if promo_type:
            return promo_type[:50]

        return None

    @staticmethod
    def _parse_price_per_unit(prod: dict[str, Any]) -> Decimal | None:
        """Extract price-per-unit from Iperal product data.

        Actual fields: priceStandardUmDisplay (per kg/l), priceUm, priceUmDisplay.
        """
        for key in ("priceStandardUmDisplay", "priceUm", "priceUmDisplay"):
            raw = prod.get(key)
            if raw is None:
                continue
            try:
                val = Decimal(str(raw).replace(",", "."))
                if val > 0:
                    return val
            except (InvalidOperation, ValueError):
                continue

        return None

    @staticmethod
    def _extract_unit_reference(prod: dict[str, Any]) -> str | None:
        """Determine the unit reference (kg, l, pz) for price-per-unit.

        Actual field: priceUnitDisplay ("pz", "kg", "l", ...).
        Also checks productInfos.WEIGHT_UNIT_SELLING as fallback.
        """
        # Primary: priceUnitDisplay
        pu = (prod.get("priceUnitDisplay") or "").strip().lower()
        if pu and pu in UNIT_MAP:
            return UNIT_MAP[pu]

        # Fallback: productInfos
        infos = prod.get("productInfos") or {}
        for key in ("WEIGHT_UNIT_BASE", "WEIGHT_UNIT_SELLING"):
            val = (infos.get(key) or "").strip().lower()
            if val and val in UNIT_MAP:
                return UNIT_MAP[val]

        return None

    # ------------------------------------------------------------------
    # Unit extraction (from original scraper, kept intact)
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_unit(description: str, product_infos: dict | None = None) -> str | None:
        """Extract a short unit string from the Iperal description."""
        if not description:
            return None

        if product_infos:
            weight = (product_infos.get("WEIGHT_SELLING") or "").strip()
            weight_unit = (product_infos.get("WEIGHT_UNIT_SELLING") or "").strip()
            if weight and weight != "0" and weight_unit:
                return f"{weight} {weight_unit}"

        first_part = description.split(",")[0].strip()

        qty_pattern = re.match(
            r"^(g|kg|ml|cl|l|pz|conf|capsule)\s+\d+(?:[.,]\d+)?",
            first_part,
            re.IGNORECASE,
        )
        if qty_pattern:
            return qty_pattern.group(0).strip()

        qty_pattern2 = re.match(
            r"^\d+(?:[.,]\d+)?\s*(g|kg|ml|cl|l|pz|conf|capsule)\b",
            first_part,
            re.IGNORECASE,
        )
        if qty_pattern2:
            return qty_pattern2.group(0).strip()

        confezione = re.search(
            r"(\d+(?:[.,]\d+)?\s*(?:g|kg|ml|cl|l|pz))",
            first_part,
            re.IGNORECASE,
        )
        if confezione:
            return confezione.group(1).strip()

        if len(first_part) <= 50:
            return first_part or None

        return None
