"""Carrefour scraper -- extracts promotional offers from carrefour.it/promozioni/.

Source: https://www.carrefour.it/promozioni/
Platform: Salesforce Commerce Cloud (Demandware).

Strategy:
    Server-rendered product cards with client-side pagination via hash
    parameters (#size=N&position=M).  We use Playwright to navigate
    and scroll through products, extracting card data from the DOM.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from app.database import async_session
from app.models.chain import Chain
from app.models.flyer import Flyer
from app.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class CarrefourScraper(BaseScraper):
    """Scraper for Carrefour Italy promotional offers."""

    name = "Carrefour"
    slug = "carrefour"
    base_url = "https://www.carrefour.it/promozioni/"

    # Load a large batch to minimize pagination rounds
    BATCH_SIZE = 200
    MAX_PRODUCTS = 3000  # safety cap

    def __init__(self, *, store_id: uuid.UUID | None = None) -> None:
        self.store_id = store_id
        super().__init__()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def scrape(self) -> list[dict[str, Any]]:
        """Extract all promotional offers from carrefour.it."""
        flyers_data: list[dict[str, Any]] = []

        try:
            page = await self._new_page()
            products = await self._extract_all_promotions(page)

            if not products:
                logger.warning("Carrefour: no products extracted.")
                return []

            today = date.today()
            days_since_monday = today.weekday()
            valid_from = today - timedelta(days=days_since_monday)
            valid_to = valid_from + timedelta(days=13)

            flyer_data = {
                "chain": self.name,
                "slug": self.slug,
                "title": "Promozioni Carrefour",
                "source_url": self.base_url,
                "valid_from": valid_from,
                "valid_to": valid_to,
                "products": products,
                "image_paths": [],
                "store_id": self.store_id,
            }
            await self._persist_offers(flyer_data)
            flyers_data.append(flyer_data)

        except Exception:
            logger.exception("Carrefour scraping failed.")
        finally:
            await self.close()

        return flyers_data

    # ------------------------------------------------------------------
    # Extraction
    # ------------------------------------------------------------------

    async def _extract_all_promotions(self, page: Page) -> list[dict[str, Any]]:
        """Navigate to promotions page and extract all products via pagination."""
        all_products: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        position = 0

        while position < self.MAX_PRODUCTS:
            url = f"{self.base_url}#size={self.BATCH_SIZE}&position={position}"
            logger.info("Carrefour: loading %s", url)

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except (PlaywrightTimeout, Exception) as exc:
                logger.warning("Carrefour: page load failed at position %d: %s", position, exc)
                break

            if position == 0:
                await self._accept_cookies(page)

            # Wait for product cards to appear
            try:
                await page.wait_for_selector(
                    "article, .product-card, [class*='product']",
                    timeout=15000,
                )
            except (PlaywrightTimeout, Exception):
                logger.info("Carrefour: no product cards at position %d, stopping.", position)
                break

            await page.wait_for_timeout(3000)

            # Scroll down to trigger lazy-loading of images and content
            for _ in range(10):
                prev_h = await page.evaluate("document.body.scrollHeight")
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(800)
                new_h = await page.evaluate("document.body.scrollHeight")
                if new_h == prev_h:
                    break

            # Extract product cards
            batch = await self._extract_product_cards(page)
            if not batch:
                logger.info("Carrefour: empty batch at position %d, stopping.", position)
                break

            # Dedup across batches
            new_count = 0
            for prod in batch:
                key = prod["name"].lower().strip()
                if key not in seen_names:
                    seen_names.add(key)
                    all_products.append(prod)
                    new_count += 1

            logger.info(
                "Carrefour: position %d — %d products (%d new, %d total).",
                position, len(batch), new_count, len(all_products),
            )

            # If we got fewer than half the batch size, we've reached the end
            if new_count < self.BATCH_SIZE // 4:
                break

            position += self.BATCH_SIZE

        logger.info("Carrefour: extracted %d total products.", len(all_products))
        return all_products

    async def _extract_product_cards(self, page: Page) -> list[dict[str, Any]]:
        """Extract product data from rendered DOM."""
        raw_products = await page.evaluate("""() => {
            const results = [];
            const seen = new Set();

            // Carrefour uses <article> or list items for product cards
            // Try multiple selectors
            const cardSelectors = [
                'article',
                '.product-card',
                '[class*="product-tile"]',
                'li[class*="product"]',
                '[data-pid]',
            ];

            let cards = [];
            for (const sel of cardSelectors) {
                const els = document.querySelectorAll(sel);
                if (els.length > 5) {
                    cards = Array.from(els);
                    break;
                }
            }

            // Fallback: look for elements containing price patterns
            if (cards.length === 0) {
                const allDivs = document.querySelectorAll('div, li');
                cards = Array.from(allDivs).filter(el => {
                    const t = el.innerText || '';
                    return t.includes('€') && t.length > 20 && t.length < 600;
                });
            }

            const priceRe = /(\\d+[,.]\\d{2})/;

            for (const card of cards) {
                const text = card.innerText || '';
                if (text.length < 10) continue;

                // Name: h3, h4, or product-name class
                let name = '';
                const nameEl = card.querySelector(
                    'h3, h4, [class*="product-name"], [class*="title"], [class*="name"]'
                );
                if (nameEl) name = nameEl.innerText.trim();

                if (!name) {
                    // First non-price, non-trivial line
                    const lines = text.split('\\n').map(l => l.trim()).filter(
                        l => l.length > 3 && !l.match(/^[€\\d.,\\s%]+$/) &&
                             !l.match(/^(OFFERTA|PAYBACK|Aggiungi|Fino al)/)
                    );
                    name = lines[0] || '';
                }

                name = name.trim();
                if (!name || name.length < 3) continue;
                const key = name.toLowerCase();
                if (seen.has(key)) continue;
                seen.add(key);

                // Prices
                let offerPrice = null;
                let originalPrice = null;

                // Look for specific price elements
                const promoPriceEl = card.querySelector(
                    '[class*="promo-price"], [class*="sale-price"], [class*="price--sale"], ' +
                    '[class*="price-current"], .price strong, .price b'
                );
                if (promoPriceEl) {
                    const m = promoPriceEl.innerText.match(priceRe);
                    if (m) offerPrice = m[1];
                }

                const origPriceEl = card.querySelector(
                    '[class*="original"], [class*="strike"], [class*="was"], ' +
                    'del, s, [class*="price--old"]'
                );
                if (origPriceEl) {
                    const m = origPriceEl.innerText.match(priceRe);
                    if (m) originalPrice = m[1];
                }

                // Fallback: scan text for "Prezzo originale: € X,XX"
                const origMatch = text.match(/Prezzo originale[:\\s]*€?\\s*(\\d+[,.]\\d{2})/i);
                if (origMatch && !originalPrice) originalPrice = origMatch[1];

                // Fallback: find all prices and pick the best
                if (!offerPrice) {
                    const allPrices = text.match(/€\\s*(\\d+[,.]\\d{2})/g);
                    if (allPrices && allPrices.length > 0) {
                        // First € price is typically the offer price
                        const first = allPrices[0].match(priceRe);
                        if (first) offerPrice = first[1];
                    }
                }

                if (!offerPrice) continue;

                // Discount percentage
                let discount = null;
                const discText = text.match(/(?:sconto|-)\\s*(\\d+)\\s*%/i);
                if (discText) discount = discText[1];

                // Quantity / unit
                let quantity = null;
                const qtyMatch = text.match(
                    /(\\d+(?:[,.]\\d+)?\\s*(?:g|kg|ml|l|cl|pz|pezzi|conf|capsule|rotoli|bustine|x\\s*\\d+)\\b)/i
                );
                if (qtyMatch) quantity = qtyMatch[1];

                // Price per unit
                let pricePerUnit = null;
                const ppuMatch = text.match(/€\\s*(\\d+[,.]\\d{2})\\s*(?:al|per|\\/)\\s*(?:kg|l|lt)/i);
                if (ppuMatch) pricePerUnit = ppuMatch[1];

                // Validity date
                let validTo = null;
                const validMatch = text.match(/Fino al\\s+(\\d{1,2})[/](\\d{1,2})[/](\\d{4})/);
                if (validMatch) validTo = validMatch[3] + '-' + validMatch[2] + '-' + validMatch[1];

                // Image
                let imgUrl = null;
                const img = card.querySelector('img');
                if (img) imgUrl = img.src || img.getAttribute('data-src') || null;

                // Brand extraction: sometimes brand is repeated before product name
                let brand = null;
                const brandEl = card.querySelector('[class*="brand"]');
                if (brandEl) brand = brandEl.innerText.trim();

                results.push({
                    name: name,
                    brand: brand,
                    offer_price: offerPrice,
                    original_price: originalPrice,
                    discount_pct: discount,
                    quantity: quantity,
                    price_per_unit: pricePerUnit,
                    valid_to: validTo,
                    image_url: imgUrl,
                    raw_text: text.substring(0, 500),
                });
            }

            return results;
        }""")

        # Parse and normalize in Python
        from app.services.product_matcher import ProductMatcher

        parsed: list[dict[str, Any]] = []
        for item in raw_products:
            name = (item.get("name") or "").strip()
            if not name or len(name) < 3:
                continue

            offer_price = self.normalize_price(item.get("offer_price"))
            if offer_price is None:
                continue

            original_price = self.normalize_price(item.get("original_price"))
            if original_price and original_price < offer_price:
                original_price, offer_price = offer_price, original_price

            # Brand: from DOM or from name
            brand = (item.get("brand") or "").strip() or None
            if not brand:
                brand, clean_name = ProductMatcher.extract_brand_from_name(name)
                name = clean_name or name

            discount_pct = None
            if item.get("discount_pct"):
                try:
                    discount_pct = Decimal(item["discount_pct"])
                except Exception:
                    pass

            parsed.append({
                "name": name,
                "brand": brand,
                "category": None,
                "original_price": str(original_price) if original_price else None,
                "offer_price": str(offer_price),
                "discount_pct": str(discount_pct) if discount_pct else None,
                "discount_type": "percentage" if discount_pct else None,
                "quantity": item.get("quantity"),
                "price_per_unit": item.get("price_per_unit"),
                "raw_text": item.get("raw_text", ""),
                "confidence": 0.85,
                "image_url": item.get("image_url"),
            })

        return parsed

    # ------------------------------------------------------------------
    # Cookie consent
    # ------------------------------------------------------------------

    async def _accept_cookies(self, page: Page) -> None:
        selectors = [
            "button#onetrust-accept-btn-handler",
            "button:has-text('Accetta tutti')",
            "button:has-text('Accetta')",
            "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
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
    # Database persistence
    # ------------------------------------------------------------------

    async def _persist_offers(self, flyer_data: dict[str, Any]) -> None:
        """Persist extracted offers (same pattern as other scrapers)."""
        from app.models.offer import Offer
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
                    "Carrefour flyer already exists (id=%s), skipping.", existing.id
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

                    brand = (prod_data.get("brand") or "").strip() or None

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

                    discount_pct = self.normalize_discount_pct(
                        prod_data.get("discount_pct")
                    )
                    original_price = self.normalize_price(
                        prod_data.get("original_price")
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
                        price_per_unit=self.normalize_price(
                            prod_data.get("price_per_unit")
                        ),
                        valid_from=valid_from,
                        valid_to=valid_to,
                        raw_text=prod_data.get("raw_text", "")[:500],
                        confidence=Decimal(str(prod_data.get("confidence", 0.85))),
                    )
                    session.add(offer)
                    saved += 1
                except Exception:
                    logger.exception(
                        "Failed to save Carrefour product: %s",
                        prod_data.get("name"),
                    )

            flyer = await session.get(Flyer, flyer_id)
            if flyer:
                flyer.status = "processed"
            await session.commit()

        logger.info("Carrefour: persisted %d products (flyer %s).", saved, flyer_id)
