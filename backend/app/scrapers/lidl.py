"""Lidl scraper -- extracts weekly offers from all sections.

Strategy:
    1. Navigate to https://www.lidl.it homepage.
    2. Discover ALL offer page links: weekly offers, thematic, "da lunedi",
       "da giovedi", and any other promotional sections.
    3. Also navigate directly to known offer URL patterns.
    4. Navigate to each offer page.
    5. Scroll fully to load all lazy content.
    6. Extract product data from .odsc-tile cards using innerText parsing.
    7. Parse prices with regex (offer price = starred price, original = first €).
    8. Persist products and offers to the database.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from app.config import get_settings
from app.database import async_session
from app.models.chain import Chain
from app.models.flyer import Flyer
from app.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Known Lidl offer section URLs to try directly.
# These are stable category pages that contain .odsc-tile product cards.
# The /c/super-offerte-kw-XX-YY/... URLs rotate weekly and are discovered
# from the homepage via _discover_offer_urls.
KNOWN_OFFER_PATHS = [
    "/c/cibo-e-bevande/s10068374",          # Food & drinks category (always available)
    "/c/cucina-e-casalinghi/s10068166",      # Kitchen & homeware
    "/c/casa-e-arredo/s10068371",            # Home & decor
]


class LidlScraper(BaseScraper):
    """Scraper for Lidl Italia weekly offers -- all sections."""

    name = "Lidl"
    slug = "lidl"
    base_url = "https://www.lidl.it"

    def __init__(self, *, store_id: uuid.UUID | None = None) -> None:
        self.store_id = store_id
        super().__init__()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def scrape(self) -> list[dict[str, Any]]:
        """Run the full Lidl scraping workflow across all sections."""
        flyers_data: list[dict[str, Any]] = []

        try:
            page = await self._new_page()
            logger.info("Navigating to Lidl homepage: %s", self.base_url)
            await page.goto(self.base_url, wait_until="domcontentloaded", timeout=30000)
            await self._accept_cookies(page)
            await page.wait_for_timeout(2000)

            # Discover offer page URLs from the homepage
            offer_urls = await self._discover_offer_urls(page)

            # Also add known offer paths that might not be linked from homepage
            for path in KNOWN_OFFER_PATHS:
                full_url = f"{self.base_url}{path}"
                if full_url not in offer_urls:
                    offer_urls.append(full_url)

            logger.info(
                "Total offer URLs to process: %d (discovered + known)",
                len(offer_urls),
            )
            await page.close()

            for url in offer_urls:
                try:
                    flyer_data = await self._process_offer_page(url)
                    if flyer_data:
                        flyers_data.append(flyer_data)
                except Exception:
                    logger.exception("Error processing Lidl offer page: %s", url)

        except Exception:
            logger.exception("Lidl scraping failed.")
        finally:
            await self.close()

        total_products = sum(len(f.get("products", [])) for f in flyers_data)
        logger.info(
            "Lidl scraping complete: %d sections, %d total products.",
            len(flyers_data),
            total_products,
        )
        return flyers_data

    # ------------------------------------------------------------------
    # Cookie consent
    # ------------------------------------------------------------------

    async def _accept_cookies(self, page: Page) -> None:
        """Dismiss cookie consent dialogs."""
        selectors = [
            "button#onetrust-accept-btn-handler",
            "button:has-text('Accetta tutti')",
            "button:has-text('Accetta')",
            "button[data-testid='cookie-accept-all']",
        ]
        for sel in selectors:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=3000):
                    await btn.click()
                    await page.wait_for_timeout(1000)
                    return
            except (PlaywrightTimeout, Exception):
                continue

    # ------------------------------------------------------------------
    # Discover offer URLs from homepage
    # ------------------------------------------------------------------

    async def _discover_offer_urls(self, page: Page) -> list[str]:
        """Find ALL offer page links on the Lidl homepage.

        Looks for links matching patterns like:
            /c/super-offerte-kw-08-26/a10088983
            /c/offerte-della-settimana/...
            /c/da-lunedi/...
            /c/da-giovedi/...
        """
        urls: list[str] = []
        seen: set[str] = set()

        # Patterns that match Lidl offer page URLs (current site structure)
        link_patterns = [
            "a[href*='/c/super-offerte']",
            "a[href*='/c/offerte']",
            "a[href*='/c/da-lunedi']",
            "a[href*='/c/da-giovedi']",
            "a[href*='/c/cibo-e-bevande']",
        ]

        for selector in link_patterns:
            links = page.locator(selector)
            count = await links.count()
            for i in range(count):
                link = links.nth(i)
                try:
                    href = await link.get_attribute("href") or ""
                    if not href:
                        continue
                    full_url = href if href.startswith("http") else f"https://www.lidl.it{href}"
                    if full_url not in seen:
                        seen.add(full_url)
                        urls.append(full_url)
                except Exception:
                    continue

        # Broader search for any offer-related links we might have missed
        if len(urls) < 3:
            logger.info("Few offer URLs found, trying broader search.")
            all_links = page.locator("a[href*='/c/']")
            count = await all_links.count()
            for i in range(count):
                try:
                    href = await all_links.nth(i).get_attribute("href") or ""
                    if re.search(r"/c/.*(?:offert|lunedi|giovedi|super|promo)", href, re.IGNORECASE):
                        full_url = href if href.startswith("http") else f"https://www.lidl.it{href}"
                        if full_url not in seen:
                            seen.add(full_url)
                            urls.append(full_url)
                except Exception:
                    continue

        logger.info("Discovered %d offer URLs from homepage.", len(urls))
        return urls

    # ------------------------------------------------------------------
    # Process a single offer page
    # ------------------------------------------------------------------

    async def _process_offer_page(self, url: str) -> dict[str, Any] | None:
        """Navigate to an offer page and extract products from .odsc-tile cards."""
        logger.info("Processing Lidl offer page: %s", url)

        page = await self._new_page()
        try:
            resp = await page.goto(url, wait_until="networkidle", timeout=30000)

            # Skip 404 or error pages
            if resp and resp.status >= 400:
                logger.info("Lidl page returned %d, skipping: %s", resp.status, url)
                return None

            await self._accept_cookies(page)
            await page.wait_for_timeout(2000)

            # Scroll to load ALL lazy content (increased depth)
            await self._scroll_to_bottom(page)

            # Extract products from .odsc-tile cards (proven working selector)
            products = await self._extract_products_from_tiles(page)

            # Fallback to other selectors if .odsc-tile didn't work
            if not products:
                products = await self._extract_products_from_html(page)

            if not products:
                logger.info("No products found on page: %s", url)
                return None

            # Determine validity dates (Lidl flyers are typically Mon-Sun)
            today = date.today()
            days_since_monday = today.weekday()
            valid_from = today - timedelta(days=days_since_monday)
            valid_to = valid_from + timedelta(days=6)

            # Extract a title from the URL or page
            title = await self._extract_page_title(page, url)

            flyer_data = {
                "chain": self.name,
                "slug": self.slug,
                "title": title,
                "source_url": url,
                "valid_from": valid_from,
                "valid_to": valid_to,
                "products": products,
                "image_paths": [],
                "store_id": self.store_id,
            }

            await self._persist_offers(flyer_data)
            return flyer_data

        except PlaywrightTimeout:
            logger.warning("Timeout loading Lidl page: %s", url)
            return None
        finally:
            await page.close()

    async def _extract_page_title(self, page: Page, url: str) -> str:
        """Extract a meaningful title from the page."""
        try:
            h1 = page.locator("h1").first
            if await h1.is_visible(timeout=2000):
                title = (await h1.inner_text()).strip()
                if title:
                    return title
        except Exception:
            pass

        # Fall back to extracting from URL
        match = re.search(r"/c/([^/]+)", url)
        if match:
            return match.group(1).replace("-", " ").title()
        return "Offerte Lidl"

    # ------------------------------------------------------------------
    # Primary extraction: .odsc-tile cards with innerText parsing
    # ------------------------------------------------------------------

    async def _extract_products_from_tiles(self, page: Page) -> list[dict[str, Any]]:
        """Extract products from .odsc-tile cards using innerText regex parsing.

        This is the proven working method from manual testing. Each tile's
        innerText contains the product info in a predictable format:
            Product Name
            Brand/description
            X,XX €*        (offer price, starred)
            Y,YY €         (original price)
            -ZZ%           (discount)
        """
        products: list[dict[str, Any]] = []

        tiles = page.locator(".odsc-tile")
        count = await tiles.count()

        if count == 0:
            logger.info("No .odsc-tile elements found.")
            return products

        logger.info("Found %d .odsc-tile elements.", count)

        for i in range(count):
            tile = tiles.nth(i)
            try:
                text = await tile.inner_text()
                if not text or len(text.strip()) < 5:
                    continue

                product = self._parse_tile_text(text)
                if product:
                    # Try to get image URL
                    image_url = await self._get_tile_image(tile)
                    if image_url:
                        product["image_url"] = image_url
                    products.append(product)

            except Exception:
                logger.debug("Failed to parse .odsc-tile %d", i)

        logger.info("Extracted %d products from .odsc-tile cards.", len(products))
        return products

    def _parse_tile_text(self, text: str) -> dict[str, Any] | None:
        """Parse the innerText of a single .odsc-tile card.

        Returns a product dict or None if parsing fails.
        """
        lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
        if len(lines) < 2:
            return None

        # The product name is typically the first non-empty line
        name = lines[0]

        # Skip tiles that look like navigation/UI elements
        skip_patterns = ["scopri", "vedi tutto", "carica", "mostra", "filtro"]
        if any(p in name.lower() for p in skip_patterns):
            return None

        # Extract offer price: number followed by €* (starred = offer price)
        offer_price = None
        offer_match = re.search(r"(\d+[,\.]\d{2})\s*€\*", text)
        if offer_match:
            offer_price = self.normalize_price(offer_match.group(1))

        # If no starred price, look for any price
        if offer_price is None:
            price_matches = re.findall(r"(\d+[,\.]\d{2})\s*€", text)
            if price_matches:
                # Take the lowest price as the offer price
                prices = []
                for pm in price_matches:
                    p = self.normalize_price(pm)
                    if p is not None:
                        prices.append(p)
                if prices:
                    offer_price = min(prices)

        if offer_price is None:
            return None

        # Extract original price: a non-starred € price that's higher than offer
        original_price = None
        all_prices = re.findall(r"(\d+[,\.]\d{2})\s*€(?!\*)", text)
        for raw_p in all_prices:
            p = self.normalize_price(raw_p)
            if p is not None and p > offer_price:
                original_price = p
                break

        # Extract discount percentage
        discount_pct = None
        discount_match = re.search(r"-\s*(\d+)\s*%", text)
        if discount_match:
            discount_pct = Decimal(discount_match.group(1))

        # Extract brand (usually second line if it looks like a brand)
        brand = None
        if len(lines) > 1:
            second_line = lines[1]
            # If the second line doesn't contain a price, it's likely brand/description
            if not re.search(r"\d+[,\.]\d{2}\s*€", second_line):
                brand = second_line

        # Extract quantity info
        quantity = None
        qty_match = re.search(
            r"(\d+(?:[,\.]\d+)?\s*(?:g|kg|ml|l|cl|pz|pezzi|conf)\b)",
            text,
            re.IGNORECASE,
        )
        if qty_match:
            quantity = qty_match.group(1)

        # Extract price per unit (€/kg, €/l, etc.)
        price_per_unit = None
        ppu_match = re.search(
            r"(\d+[,\.]\d{2})\s*€\s*/\s*(?:kg|l|lt)",
            text,
            re.IGNORECASE,
        )
        if ppu_match:
            price_per_unit = self.normalize_price(ppu_match.group(1))

        return {
            "name": name.strip(),
            "brand": brand.strip() if brand else None,
            "category": None,
            "original_price": str(original_price) if original_price else None,
            "offer_price": str(offer_price),
            "discount_pct": str(discount_pct) if discount_pct else None,
            "discount_type": "percentage" if discount_pct else None,
            "quantity": quantity,
            "price_per_unit": str(price_per_unit) if price_per_unit else None,
            "raw_text": text[:500],
            "confidence": 0.9,
            "image_url": None,
        }

    async def _get_tile_image(self, tile) -> str | None:
        """Extract the image URL from a tile element."""
        for img_sel in ["img", "picture source", "picture img"]:
            try:
                img = tile.locator(img_sel).first
                if await img.is_visible(timeout=500):
                    url = (
                        await img.get_attribute("src")
                        or await img.get_attribute("data-src")
                        or await img.get_attribute("srcset")
                    )
                    if url:
                        if url.startswith("//"):
                            url = f"https:{url}"
                        return url
            except Exception:
                continue
        return None

    # ------------------------------------------------------------------
    # Fallback: structured HTML selectors
    # ------------------------------------------------------------------

    async def _extract_products_from_html(self, page: Page) -> list[dict[str, Any]]:
        """Fallback extraction using structured HTML selectors."""
        products: list[dict[str, Any]] = []

        card_selectors = [
            ".product-grid-box",
            ".ACampaignGrid__item",
            "[data-grid-box]",
            ".AProductCard",
            "article.product",
            ".ods-tile",
        ]

        for sel in card_selectors:
            cards = page.locator(sel)
            count = await cards.count()
            if count == 0:
                continue

            logger.info("Fallback: found %d cards with selector '%s'", count, sel)

            for i in range(count):
                card = cards.nth(i)
                try:
                    product = await self._parse_product_card(card)
                    if product:
                        products.append(product)
                except Exception:
                    logger.debug("Failed to parse fallback card %d", i)

            if products:
                break

        logger.info("Fallback extraction: %d products found.", len(products))
        return products

    async def _parse_product_card(self, card) -> dict[str, Any] | None:
        """Extract data from a single product card element (fallback)."""
        name_selectors = [
            ".product-grid-box__title",
            ".ACampaignGrid__name",
            "[data-testid='product-title']",
            "h3",
            ".product-title",
            ".lidl-m-pricebox__title",
        ]
        name = await self._first_text(card, name_selectors)
        if not name:
            return None

        price_selectors = [
            ".m-price__price",
            ".pricebox__price",
            "[data-testid='product-price']",
            ".lidl-m-pricebox__price",
            ".price--action",
            ".price",
        ]
        raw_price = await self._first_text(card, price_selectors)
        offer_price = self.normalize_price(raw_price)
        if offer_price is None:
            return None

        original_selectors = [".m-price__rrp", ".pricebox__strikethrough", ".price--old", "del", "s"]
        raw_original = await self._first_text(card, original_selectors)
        original_price = self.normalize_price(raw_original)

        discount_selectors = [".m-price__discount", ".pricebox__discount", ".badge--discount"]
        raw_discount = await self._first_text(card, discount_selectors)
        discount_pct = self.normalize_discount_pct(raw_discount)

        brand_selectors = [".product-grid-box__sub-title", ".ACampaignGrid__brand", ".product-brand"]
        brand = await self._first_text(card, brand_selectors)

        return {
            "name": name.strip(),
            "brand": brand.strip() if brand else None,
            "category": None,
            "original_price": str(original_price) if original_price else None,
            "offer_price": str(offer_price),
            "discount_pct": str(discount_pct) if discount_pct else None,
            "discount_type": "percentage" if discount_pct else None,
            "quantity": None,
            "price_per_unit": None,
            "raw_text": name,
            "confidence": 0.85,
            "image_url": None,
        }

    async def _first_text(self, parent, selectors: list[str]) -> str | None:
        """Return the inner text of the first visible element matching any selector."""
        for sel in selectors:
            try:
                el = parent.locator(sel).first
                if await el.is_visible(timeout=300):
                    text = (await el.inner_text()).strip()
                    if text:
                        return text
            except Exception:
                continue
        return None

    # ------------------------------------------------------------------
    # Scroll helper -- increased depth for full content loading
    # ------------------------------------------------------------------

    async def _scroll_to_bottom(self, page: Page, max_scrolls: int = 30) -> None:
        """Gradually scroll down to trigger lazy loading of ALL product cards.

        Increased from 15 to 30 scrolls and added a stall counter so we
        don't stop too early on pages with many lazy-loaded tiles.
        """
        stall_count = 0
        for _ in range(max_scrolls):
            prev_height = await page.evaluate("document.body.scrollHeight")
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1500)
            new_height = await page.evaluate("document.body.scrollHeight")
            if new_height == prev_height:
                stall_count += 1
                if stall_count >= 3:
                    break
            else:
                stall_count = 0

    # ------------------------------------------------------------------
    # Database persistence
    # ------------------------------------------------------------------

    async def _persist_offers(self, flyer_data: dict[str, Any]) -> None:
        """Create a Flyer row and persist extracted product offers.

        Uses date-based dedup so re-scraping the same section in a new
        week creates new offer rows, building price history.
        """
        from sqlalchemy import select, and_

        store_id = flyer_data.get("store_id") or self.store_id
        valid_from = flyer_data.get("valid_from") or date.today()
        valid_to = flyer_data.get("valid_to") or date.today()

        async with async_session() as session:
            stmt = select(Chain).where(Chain.slug == self.slug)
            result = await session.execute(stmt)
            chain = result.scalar_one_or_none()

            if chain is None:
                logger.error("Chain '%s' not found in DB.", self.slug)
                return

            # Date-based dedup: same source + same date range = skip
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
                    "Flyer already exists for URL %s (%s to %s, id=%s), skipping.",
                    flyer_data["source_url"],
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

        products = flyer_data.get("products", [])
        if products:
            await self._save_html_products(
                products=products,
                flyer_id=flyer_id,
                chain_id=chain_id,
                store_id=store_id,
                valid_from=valid_from,
                valid_to=valid_to,
            )

    async def _save_html_products(
        self,
        products: list[dict[str, Any]],
        flyer_id: uuid.UUID,
        chain_id: uuid.UUID,
        store_id: uuid.UUID | None = None,
        valid_from=None,
        valid_to=None,
    ) -> None:
        """Save extracted products to the database."""
        from app.models.offer import Offer

        saved_count = 0
        async with async_session() as session:
            for prod_data in products:
                try:
                    name = (prod_data.get("name") or "").strip()
                    if not name:
                        continue

                    raw_offer = prod_data.get("offer_price")
                    offer_price = self.normalize_price(raw_offer)
                    if offer_price is None:
                        continue

                    brand = (prod_data.get("brand") or "").strip() or None

                    # Find or create product (fuzzy dedup via ProductMatcher)
                    product = await self._find_or_create_product(
                        {
                            "name": name,
                            "brand": brand,
                            "category": prod_data.get("category"),
                            "unit": prod_data.get("quantity"),
                            "image_url": prod_data.get("image_url"),
                        },
                        session=session,
                    )

                    original_price = self.normalize_price(prod_data.get("original_price"))
                    discount_pct = self.normalize_discount_pct(prod_data.get("discount_pct"))
                    price_per_unit = self.normalize_price(prod_data.get("price_per_unit"))

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
                        price_per_unit=price_per_unit,
                        valid_from=valid_from,
                        valid_to=valid_to,
                        raw_text=prod_data.get("raw_text"),
                        confidence=Decimal(str(prod_data.get("confidence", 0.9))),
                    )
                    session.add(offer)
                    saved_count += 1

                except Exception:
                    logger.exception("Failed to save product: %s", prod_data.get("name"))

            # Mark flyer as processed.
            flyer = await session.get(Flyer, flyer_id)
            if flyer:
                flyer.status = "processed"

            await session.commit()

        logger.info(
            "Persisted %d products for flyer %s.",
            saved_count,
            flyer_id,
        )
