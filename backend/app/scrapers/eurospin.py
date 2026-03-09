"""Eurospin scraper -- extracts promotional offers from eurospin.it/promozioni/.

Source: https://www.eurospin.it/promozioni/
Platform: WordPress with server-rendered product cards.

Products are displayed directly in the DOM as divs with onclick handlers.
No pagination -- all ~120+ products load on a single page.
Price format: original (struck through) → offer (bold) with €.
Brand appears in parentheses or as separate text above product name.
Date ranges like "12.03 - 22.03" indicate validity period.
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


class EurospinScraper(BaseScraper):
    """Scraper for Eurospin supermarket promotional offers."""

    name = "Eurospin"
    slug = "eurospin"
    base_url = "https://www.eurospin.it/promozioni/"

    def __init__(self, *, store_id: uuid.UUID | None = None) -> None:
        self.store_id = store_id
        super().__init__()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def scrape(self) -> list[dict[str, Any]]:
        """Extract all promotional offers from eurospin.it/promozioni/."""
        flyers_data: list[dict[str, Any]] = []

        try:
            page = await self._new_page()
            logger.info("Eurospin: navigating to %s", self.base_url)

            await page.goto(self.base_url, wait_until="domcontentloaded", timeout=30000)
            await self._accept_cookies(page)
            await page.wait_for_timeout(3000)

            # Scroll to load all content
            for _ in range(8):
                prev_h = await page.evaluate("document.body.scrollHeight")
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1000)
                new_h = await page.evaluate("document.body.scrollHeight")
                if new_h == prev_h:
                    break

            # Extract products and date range
            products, date_range = await self._extract_products(page)

            if not products:
                logger.warning("Eurospin: no products extracted.")
                return []

            # Parse date range for validity
            valid_from, valid_to = self._parse_date_range(date_range)
            if not valid_from:
                today = date.today()
                days_since_monday = today.weekday()
                valid_from = today - timedelta(days=days_since_monday)
            if not valid_to:
                valid_to = valid_from + timedelta(days=13)

            flyer_data = {
                "chain": self.name,
                "slug": self.slug,
                "title": "Promozioni Eurospin",
                "source_url": self.base_url,
                "valid_from": valid_from,
                "valid_to": valid_to,
                "products": products,
                "image_paths": [],
                "store_id": self.store_id,
            }
            await self._persist_offers(flyer_data)
            flyers_data.append(flyer_data)

            logger.info(
                "Eurospin: extracted %d products (valid %s – %s).",
                len(products), valid_from, valid_to,
            )

        except Exception:
            logger.exception("Eurospin scraping failed.")
        finally:
            await self.close()

        return flyers_data

    # ------------------------------------------------------------------
    # Product extraction
    # ------------------------------------------------------------------

    async def _extract_products(self, page: Page) -> tuple[list[dict[str, Any]], str]:
        """Extract product data from the rendered DOM.

        Returns (products, date_range_string).
        """
        result = await page.evaluate("""() => {
            const products = [];
            const seen = new Set();
            let dateRange = '';

            // Extract date range from page (e.g. "12.03 - 22.03")
            const pageText = document.body.innerText || '';
            const dateMatch = pageText.match(/(\\d{1,2}[.]\\d{2})\\s*[-–]\\s*(\\d{1,2}[.]\\d{2})/);
            if (dateMatch) dateRange = dateMatch[0];

            // Date pattern to exclude from price extraction
            const datePatternStr = dateRange ? dateRange.replace(/[-–]/g, '[-–]').replace(/\\./g, '[.]') : null;

            // Eurospin cards are divs with onclick="javascript:;" containing
            // product info with € prices and product images.

            const allDivs = document.querySelectorAll('div[onclick]');
            let candidateCards = Array.from(allDivs).filter(d => {
                const t = d.innerText || '';
                return t.includes('€') && t.length > 15 && t.length < 1500;
            });

            // Fallback: broaden to any div with € and product image
            if (candidateCards.length < 10) {
                const broader = document.querySelectorAll('div, article, li');
                candidateCards = Array.from(broader).filter(d => {
                    const t = d.innerText || '';
                    const hasPrice = t.includes('€') && t.match(/\\d+[,.]\\d{2}/);
                    const hasImg = d.querySelector('img[src*="uploads/smt"], img[src*="eurospin"]');
                    return hasPrice && hasImg && t.length > 15 && t.length < 1500;
                });
            }

            const dateLineRe = /^\\d{1,2}[.]\\d{2}\\s*[-–]\\s*\\d{1,2}[.]\\d{2}$/;
            const priceLineRe = /^[€\\d.,\\s/kgl]+$/;
            const qtyLineRe = /^\\d+(?:[,.]\\d+)?\\s*(?:g|kg|ml|l|cl|pz|pezzi|conf|x\\s*\\d)\\b/i;
            const ppuLineRe = /\\d+[,.]\\d{2}\\s*€\\s*\\/\\s*(?:kg|l)/i;
            const qtyRe = /(\\d+(?:[,.]\\d+)?\\s*(?:g|kg|ml|l|cl|pz|pezzi|conf|capsule|rotoli|bustine|dosi|x\\s*\\d+\\s*(?:g|ml|l))\\b)/i;

            for (const card of candidateCards) {
                const text = card.innerText || '';
                if (text.length < 10) continue;

                const lines = text.split('\\n').map(l => l.trim()).filter(l => l.length > 0);
                if (lines.length < 3) continue;

                // Card structure (Eurospin):
                //   line 0: "12.03 - 22.03" (date range)
                //   line 1: "NOME PRODOTTO" (product name, often all-caps)
                //   line 2: "BRAND" (brand, sometimes)
                //   ...image...
                //   line N: "1,59   1,29 €" (original  offer price)
                //   line N+1: "100 g  -  14,90 €/kg" (quantity + PPU)

                let name = '';
                let brand = '';
                let priceLine = '';

                // Pass 1: find product name and brand (first text lines, skip dates)
                const textLines = [];
                for (const line of lines) {
                    if (dateLineRe.test(line)) continue;
                    if (line.includes('€')) continue;  // price lines
                    if (qtyLineRe.test(line)) continue;  // quantity lines
                    if (ppuLineRe.test(line)) continue;  // PPU lines
                    if (line.match(/^\\d+[,.]\\d{2}$/)) continue;  // bare numbers
                    if (line.length < 2) continue;
                    textLines.push(line);
                }

                if (textLines.length >= 2) {
                    // First text line = product name, second = brand (Eurospin pattern)
                    name = textLines[0];
                    brand = textLines[1];
                } else if (textLines.length === 1) {
                    name = textLines[0];
                }

                if (!name || name.length < 3) continue;

                const key = name.toLowerCase().replace(/\\s+/g, ' ');
                if (seen.has(key)) continue;
                seen.add(key);

                // Pass 2: find price line (contains € and decimal numbers)
                // EXCLUDE the date range numbers
                let offerPrice = null;
                let originalPrice = null;

                for (const line of lines) {
                    if (!line.includes('€')) continue;
                    if (ppuLineRe.test(line)) continue;  // skip PPU lines

                    // Remove date range if present in the line
                    let cleanLine = line;
                    if (dateRange) cleanLine = cleanLine.replace(dateRange, '');

                    const prices = [];
                    let m;
                    const re = /(\\d+[,.]\\d{2})/g;
                    while ((m = re.exec(cleanLine)) !== null) {
                        prices.push(m[1]);
                    }

                    if (prices.length >= 2) {
                        // original then offer
                        const p1 = parseFloat(prices[0].replace(',', '.'));
                        const p2 = parseFloat(prices[1].replace(',', '.'));
                        if (p1 > p2) {
                            originalPrice = prices[0];
                            offerPrice = prices[1];
                        } else {
                            originalPrice = prices[1];
                            offerPrice = prices[0];
                        }
                    } else if (prices.length === 1) {
                        offerPrice = prices[0];
                    }
                    if (offerPrice) break;
                }

                // If no € line found, try any line with prices (excluding date)
                if (!offerPrice) {
                    for (const line of lines) {
                        if (dateLineRe.test(line)) continue;
                        const prices = [];
                        let m;
                        const re = /(\\d+[,.]\\d{2})/g;
                        while ((m = re.exec(line)) !== null) prices.push(m[1]);
                        // Must have at least one price that's not a date component
                        const validPrices = prices.filter(p => {
                            const v = parseFloat(p.replace(',', '.'));
                            return v < 1000 && v > 0.01;
                        });
                        if (validPrices.length >= 2) {
                            const p1 = parseFloat(validPrices[0].replace(',', '.'));
                            const p2 = parseFloat(validPrices[1].replace(',', '.'));
                            if (p1 > p2) { originalPrice = validPrices[0]; offerPrice = validPrices[1]; }
                            else { originalPrice = validPrices[1]; offerPrice = validPrices[0]; }
                        } else if (validPrices.length === 1) {
                            offerPrice = validPrices[0];
                        }
                        if (offerPrice) break;
                    }
                }

                if (!offerPrice) continue;

                // Discount
                let discount = null;
                const discMatch = text.match(/(-\\s*\\d+\\s*%|sconto\\s+\\d+\\s*%)/i);
                if (discMatch) discount = discMatch[1].replace(/[^\\d]/g, '');

                // Quantity
                let quantity = null;
                for (const line of lines) {
                    if (dateLineRe.test(line)) continue;
                    const qm = line.match(qtyRe);
                    if (qm) { quantity = qm[1]; break; }
                }

                // Price per unit (e.g. "1,58 €/kg")
                let pricePerUnit = null;
                const ppuMatch = text.match(/(\\d+[,.]\\d{2})\\s*€\\s*\\/\\s*(?:kg|l|lt)/i);
                if (ppuMatch) pricePerUnit = ppuMatch[1];

                // Image (skip badge/certification images)
                let imgUrl = null;
                const imgs = card.querySelectorAll('img[src*="uploads/smt"]');
                for (const img of imgs) {
                    const src = img.src || '';
                    if (src.includes('plastica') || src.includes('badge') ||
                        src.includes('icon') || src.includes('logo') ||
                        src.includes('bio-') || src.includes('senza-')) continue;
                    imgUrl = src;
                    break;
                }

                products.push({
                    name: name,
                    brand: brand || null,
                    offer_price: offerPrice,
                    original_price: originalPrice,
                    discount_pct: discount,
                    quantity: quantity,
                    price_per_unit: pricePerUnit,
                    image_url: imgUrl,
                    raw_text: text.substring(0, 500),
                });
            }

            return {products: products, dateRange: dateRange};
        }""")

        raw_products = result.get("products", [])
        date_range = result.get("dateRange", "")

        # Normalize in Python
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

            # Brand from JS extraction or from name
            brand = (item.get("brand") or "").strip() or None
            if not brand:
                brand, clean_name = ProductMatcher.extract_brand_from_name(name)
                if clean_name:
                    name = clean_name

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
                "confidence": 0.80,
                "image_url": item.get("image_url"),
            })

        logger.info("Eurospin: parsed %d products.", len(parsed))
        return parsed, date_range

    # ------------------------------------------------------------------
    # Cookie consent
    # ------------------------------------------------------------------

    async def _accept_cookies(self, page: Page) -> None:
        selectors = [
            "button#onetrust-accept-btn-handler",
            "button:has-text('Accetta tutti')",
            "button:has-text('Accetta')",
            "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
            "button:has-text('OK')",
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
    # Date parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_date_range(date_str: str) -> tuple[date | None, date | None]:
        """Parse date range like '12.03 - 22.03' into (valid_from, valid_to).

        Assumes current year.
        """
        if not date_str:
            return None, None

        m = re.match(r"(\d{1,2})[.](\d{2})\s*[-–]\s*(\d{1,2})[.](\d{2})", date_str)
        if not m:
            return None, None

        year = date.today().year
        try:
            valid_from = date(year, int(m.group(2)), int(m.group(1)))
            valid_to = date(year, int(m.group(4)), int(m.group(3)))
            if valid_to < valid_from:
                # Cross-year (e.g. 28.12 - 10.01)
                valid_to = date(year + 1, int(m.group(4)), int(m.group(3)))
            return valid_from, valid_to
        except ValueError:
            return None, None

    # ------------------------------------------------------------------
    # Database persistence
    # ------------------------------------------------------------------

    async def _persist_offers(self, flyer_data: dict[str, Any]) -> None:
        """Persist extracted offers."""
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
                    "Eurospin flyer already exists (id=%s), skipping.", existing.id
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
                        confidence=Decimal(str(prod_data.get("confidence", 0.80))),
                    )
                    session.add(offer)
                    saved += 1
                except Exception:
                    logger.exception(
                        "Failed to save Eurospin product: %s",
                        prod_data.get("name"),
                    )

            flyer = await session.get(Flyer, flyer_id)
            if flyer:
                flyer.status = "processed"
            await session.commit()

        logger.info("Eurospin: persisted %d products (flyer %s).", saved, flyer_id)
