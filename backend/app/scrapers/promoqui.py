"""PromoQui aggregator scraper -- extracts offers from promoqui.it.

This scraper serves as an alternative data source when direct chain scraping
(Gemini OCR) is unavailable. PromoQui aggregates flyer offers from Italian
supermarkets in structured HTML format.

Supported chains: esselunga, coop, iperal, lidl
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

# Map our chain slugs to PromoQui URL slugs
PROMOQUI_CHAINS = {
    "esselunga": "esselunga",
    "coop": "coop",
    "iperal": "iperal",
    "lidl": "lidl",
}


class PromoQuiScraper(BaseScraper):
    """Scraper that pulls offers from promoqui.it for a given chain."""

    name = "PromoQui"
    slug = "promoqui"
    base_url = "https://www.promoqui.it"

    def __init__(self, chain_slug: str) -> None:
        self.chain_slug = chain_slug
        self.chain_name = chain_slug.title()
        # Override name/slug to match the actual chain
        self.name = self.chain_name
        self.slug = chain_slug
        super().__init__()

    async def scrape(self) -> list[dict[str, Any]]:
        """Scrape offers for the configured chain from PromoQui."""
        pq_slug = PROMOQUI_CHAINS.get(self.chain_slug)
        if not pq_slug:
            logger.error("Chain '%s' not supported on PromoQui.", self.chain_slug)
            return []

        url = f"{self.base_url}/offerte/{pq_slug}"
        flyers_data: list[dict[str, Any]] = []

        try:
            page = await self._new_page()
            logger.info("Navigating to PromoQui: %s", url)
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await self._accept_cookies(page)
            await page.wait_for_timeout(2000)

            # Load more offers by scrolling and clicking "load more"
            await self._load_all_offers(page)

            # Extract products
            products = await self._extract_offers(page)

            if not products:
                logger.info("No offers found for '%s' on PromoQui.", self.chain_slug)
                return []

            # Filter out non-food items (Salomon collection, etc.)
            food_products = [p for p in products if self._is_food_product(p)]
            logger.info(
                "Extracted %d total offers, %d food products for '%s'.",
                len(products),
                len(food_products),
                self.chain_slug,
            )

            # Use food products if we have enough, otherwise fall back to all
            final_products = food_products if len(food_products) >= 5 else products

            today = date.today()
            days_since_monday = today.weekday()
            valid_from = today - timedelta(days=days_since_monday)
            valid_to = valid_from + timedelta(days=13)  # 2 weeks typical

            flyer_data = {
                "chain": self.chain_name,
                "slug": self.chain_slug,
                "title": f"Offerte {self.chain_name} (PromoQui)",
                "source_url": url,
                "valid_from": valid_from,
                "valid_to": valid_to,
                "products": final_products,
                "image_paths": [],
            }

            await self._persist_offers(flyer_data)
            flyers_data.append(flyer_data)

        except Exception:
            logger.exception("PromoQui scraping failed for '%s'.", self.chain_slug)
        finally:
            await self.close()

        return flyers_data

    # ------------------------------------------------------------------
    # Cookie consent
    # ------------------------------------------------------------------

    async def _accept_cookies(self, page: Page) -> None:
        selectors = [
            "button:has-text('ACCETTO')",
            "button:has-text('Accetta')",
            "button#onetrust-accept-btn-handler",
        ]
        for sel in selectors:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=3000):
                    await btn.click()
                    await page.wait_for_timeout(500)
                    return
            except (PlaywrightTimeout, Exception):
                continue

    # ------------------------------------------------------------------
    # Load all offers (scroll + "load more" button)
    # ------------------------------------------------------------------

    async def _load_all_offers(self, page: Page, max_loads: int = 10) -> None:
        """Scroll and click 'load more' to get more offers."""
        for i in range(max_loads):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1000)

            # Try clicking "CARICA ALTRE OFFERTE"
            try:
                load_more = page.locator(
                    "button:has-text('CARICA ALTRE'), "
                    "a:has-text('CARICA ALTRE'), "
                    "button:has-text('Carica altre')"
                ).first
                if await load_more.is_visible(timeout=2000):
                    await load_more.click()
                    await page.wait_for_timeout(2000)
                    logger.debug("Loaded more offers (round %d).", i + 1)
                else:
                    break
            except (PlaywrightTimeout, Exception):
                break

    # ------------------------------------------------------------------
    # Extract offers from HTML
    # ------------------------------------------------------------------

    async def _extract_offers(self, page: Page) -> list[dict[str, Any]]:
        """Extract structured offer data from PromoQui offer cards."""
        products: list[dict[str, Any]] = []

        offers_data = await page.evaluate("""() => {
            const offerEls = document.querySelectorAll('[class*="offer__vyBiG"], [class*="OffersList_offer_"]');
            const results = [];

            for (const el of offerEls) {
                const titleEl = el.querySelector('[class*="title"]');
                const priceLabels = el.querySelectorAll('[class*="price-label"]');
                const imgEl = el.querySelector('img');

                const title = titleEl ? titleEl.innerText.trim() : '';
                if (!title) continue;

                // Get the first price (offer price)
                let offerPrice = null;
                let originalPrice = null;

                // Parse price from the text - look for the pattern X.XX€
                const text = el.innerText;
                const priceMatches = text.match(/(\\d+[,.]\\d{2})\\s*€/g);
                if (priceMatches && priceMatches.length > 0) {
                    offerPrice = priceMatches[0].replace('€', '').trim();
                }

                // Look for discount percentage
                let discount = null;
                const discountMatch = text.match(/-\\s*(\\d+)\\s*%/);
                if (discountMatch) {
                    discount = discountMatch[1];
                }

                const imgSrc = imgEl ? (imgEl.src || imgEl.getAttribute('data-src')) : null;

                results.push({
                    name: title,
                    offer_price: offerPrice,
                    discount_pct: discount,
                    image_url: imgSrc,
                    raw_text: text.substring(0, 400)
                });
            }
            return results;
        }""")

        seen_products: set[str] = set()

        for item in offers_data:
            name = item.get("name", "").strip()
            if not name or len(name) < 2:
                continue

            raw_price = item.get("offer_price")
            offer_price = self.normalize_price(raw_price)
            if offer_price is None:
                continue

            # Deduplicate by name + price
            dedup_key = f"{name.lower()}|{offer_price}"
            if dedup_key in seen_products:
                continue
            seen_products.add(dedup_key)

            discount_pct = None
            if item.get("discount_pct"):
                try:
                    discount_pct = Decimal(item["discount_pct"])
                except Exception:
                    pass

            products.append({
                "name": name,
                "brand": None,
                "category": None,
                "original_price": None,
                "offer_price": str(offer_price),
                "discount_pct": str(discount_pct) if discount_pct else None,
                "discount_type": "percentage" if discount_pct else None,
                "quantity": None,
                "price_per_unit": None,
                "raw_text": item.get("raw_text", ""),
                "confidence": 0.80,
                "image_url": item.get("image_url"),
            })

        return products

    # ------------------------------------------------------------------
    # Food product filter
    # ------------------------------------------------------------------

    @staticmethod
    def _is_food_product(product: dict[str, Any]) -> bool:
        """Heuristic to filter out non-food items (clothing, collectibles, etc.)."""
        name = (product.get("name") or "").lower()

        # Non-food keywords
        non_food = [
            "bollini", "salomon", "marsupio", "zaino", "borsa", "berretto",
            "cappellino", "scaldacollo", "cuffie", "smart tv", "tv ",
            "smartphone", "tablet", "scarpe", "abbigliamento", "maglietta",
            "pantalone", "giacca", "felpa", "set utensili",
        ]
        if any(kw in name for kw in non_food):
            return False

        # Food-positive keywords
        food_kw = [
            "latte", "pane", "pasta", "riso", "olio", "aceto", "sale",
            "zucchero", "farina", "uova", "burro", "formaggio", "yogurt",
            "carne", "pollo", "maiale", "manzo", "pesce", "salmone", "tonno",
            "frutta", "verdura", "insalata", "pomodor", "patate", "cipoll",
            "mela", "banana", "arancia", "limone",
            "biscott", "crackers", "cereali", "fette", "muffin",
            "prosciutto", "salame", "mortadella", "bresaola", "speck",
            "mozzarella", "parmigiano", "grana", "pecorino", "ricotta",
            "acqua", "birra", "vino", "succo", "caffè", "tè",
            "detersivo", "sapone", "shampoo", "dentifricio",
            "surgelat", "gelato", "pizza", "ravioli", "gnocchi",
            "nutella", "cioccolat", "caramell",
            "ketchup", "maionese", "senape",
            "conserv", "pelat", "passata", "sugo",
        ]
        if any(kw in name for kw in food_kw):
            return True

        # If price is < 20€, likely food/grocery
        try:
            price = float(product.get("offer_price", "999"))
            if price < 20:
                return True
        except (ValueError, TypeError):
            pass

        return False

    # ------------------------------------------------------------------
    # Database persistence
    # ------------------------------------------------------------------

    async def _persist_offers(self, flyer_data: dict[str, Any]) -> None:
        """Create Flyer and save products to DB."""
        from app.models.offer import Offer
        from app.models.product import Product
        from sqlalchemy import select

        async with async_session() as session:
            # Find the chain
            stmt = select(Chain).where(Chain.slug == self.chain_slug)
            result = await session.execute(stmt)
            chain = result.scalar_one_or_none()

            if chain is None:
                logger.error("Chain '%s' not found in DB.", self.chain_slug)
                return

            # Check for existing flyer from PromoQui
            source_url = flyer_data["source_url"]
            stmt_existing = select(Flyer).where(
                Flyer.source_url == source_url,
                Flyer.chain_id == chain.id,
            )
            existing = (await session.execute(stmt_existing)).scalar_one_or_none()
            if existing:
                logger.info(
                    "PromoQui flyer already exists for '%s' (id=%s), skipping.",
                    self.chain_slug,
                    existing.id,
                )
                return

            flyer = Flyer(
                chain_id=chain.id,
                title=flyer_data["title"],
                valid_from=flyer_data.get("valid_from") or date.today(),
                valid_to=flyer_data.get("valid_to") or date.today(),
                source_url=source_url,
                pages_count=1,
                status="processing",
            )
            session.add(flyer)
            await session.commit()
            await session.refresh(flyer)

            flyer_id = flyer.id
            chain_id = chain.id

        # Save products
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

                    # Find or create product
                    stmt = select(Product).where(Product.name == name)
                    if brand:
                        stmt = stmt.where(Product.brand == brand)
                    result = await session.execute(stmt.limit(1))
                    product = result.scalar_one_or_none()

                    if product is None:
                        product = Product(
                            name=name,
                            brand=brand,
                            category=prod_data.get("category"),
                            unit=prod_data.get("quantity"),
                            image_url=prod_data.get("image_url"),
                        )
                        session.add(product)
                        await session.flush()

                    discount_pct = self.normalize_discount_pct(prod_data.get("discount_pct"))
                    original_price = self.normalize_price(prod_data.get("original_price"))

                    offer = Offer(
                        product_id=product.id,
                        flyer_id=flyer_id,
                        chain_id=chain_id,
                        original_price=original_price,
                        offer_price=offer_price,
                        discount_pct=discount_pct,
                        discount_type=prod_data.get("discount_type"),
                        quantity=prod_data.get("quantity"),
                        price_per_unit=None,
                        valid_from=flyer_data.get("valid_from"),
                        valid_to=flyer_data.get("valid_to"),
                        raw_text=prod_data.get("raw_text", "")[:500],
                        confidence=Decimal(str(prod_data.get("confidence", 0.8))),
                    )
                    session.add(offer)
                    saved += 1

                except Exception:
                    logger.exception("Failed to save product: %s", prod_data.get("name"))

            flyer = await session.get(Flyer, flyer_id)
            if flyer:
                flyer.status = "processed"

            await session.commit()

        logger.info(
            "PromoQui: persisted %d products for '%s' (flyer %s).",
            saved,
            self.chain_slug,
            flyer_id,
        )
