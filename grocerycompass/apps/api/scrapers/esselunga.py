"""Esselunga scraper using Playwright for JS-heavy pages."""

import re
import logging
from datetime import datetime
from typing import AsyncIterator

from scrapers.base import BaseSupermarketScraper, RawProduct
from scrapers.browser import get_stealth_browser, close_browser

logger = logging.getLogger(__name__)

# Known category URLs for Esselunga online store
ESSELUNGA_CATEGORIES = [
    {"name": "Frutta e Verdura", "url": "/categoria/frutta-e-verdura"},
    {"name": "Carne", "url": "/categoria/carne"},
    {"name": "Pesce", "url": "/categoria/pesce"},
    {"name": "Latticini e Uova", "url": "/categoria/latticini-e-uova"},
    {"name": "Pane e Pasticceria", "url": "/categoria/pane-e-pasticceria"},
    {"name": "Pasta, Riso e Cereali", "url": "/categoria/pasta-riso-e-cereali"},
    {"name": "Olio, Aceto e Condimenti", "url": "/categoria/olio-aceto-e-condimenti"},
    {"name": "Conserve e Sughi", "url": "/categoria/conserve-e-sughi"},
    {"name": "Bevande", "url": "/categoria/bevande"},
    {"name": "Surgelati", "url": "/categoria/surgelati"},
    {"name": "Snack e Dolci", "url": "/categoria/snack-e-dolci"},
    {"name": "Colazione", "url": "/categoria/colazione"},
    {"name": "Igiene e Bellezza", "url": "/categoria/igiene-e-bellezza"},
    {"name": "Casa e Pulizia", "url": "/categoria/casa-e-pulizia"},
]

BASE_URL = "https://www.esselunga.it/it-it/prodotti"


class EsselungaScraper(BaseSupermarketScraper):
    CHAIN_SLUG = "esselunga"
    RATE_LIMIT_DELAY = 3.0  # Higher delay — Esselunga is strict

    async def scrape_all_products(self) -> AsyncIterator[RawProduct]:
        """Scrape all products across all categories."""
        playwright, browser, context = await get_stealth_browser()

        try:
            for category in ESSELUNGA_CATEGORIES:
                self.logger.info(f"Scraping category: {category['name']}")
                try:
                    products = await self._scrape_category_page(
                        context, category["url"], category["name"]
                    )
                    for product in products:
                        self.products_scraped += 1
                        yield product
                except Exception as e:
                    self.logger.error(f"Error scraping {category['name']}: {e}")
                    self.errors.append(str(e))

                await self.rate_limit()
        finally:
            await close_browser(playwright, browser)

    async def scrape_category(self, category_url: str) -> list[RawProduct]:
        """Scrape a single category."""
        playwright, browser, context = await get_stealth_browser()
        try:
            return await self._scrape_category_page(context, category_url, "")
        finally:
            await close_browser(playwright, browser)

    async def _scrape_category_page(
        self, context, category_path: str, category_name: str
    ) -> list[RawProduct]:
        """Scrape products from a single category page using Playwright."""
        page = await context.new_page()
        products = []

        try:
            url = f"{BASE_URL}{category_path}"
            await page.goto(url, wait_until="networkidle", timeout=30000)

            # Accept cookies if present
            try:
                cookie_btn = page.locator('[data-testid="cookie-accept"]')
                if await cookie_btn.is_visible(timeout=3000):
                    await cookie_btn.click()
            except Exception:
                pass

            # Scroll to load lazy-loaded products
            prev_count = 0
            for _ in range(20):  # Max 20 scroll iterations
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1500)

                product_cards = page.locator('[data-testid="product-card"]')
                count = await product_cards.count()
                if count == prev_count:
                    break
                prev_count = count

            # Extract product data
            product_cards = page.locator('[data-testid="product-card"]')
            count = await product_cards.count()
            self.logger.info(f"Found {count} products in {category_name}")

            for i in range(count):
                try:
                    card = product_cards.nth(i)
                    product = await self._parse_product_card(card, category_name)
                    if product and product.price > 0:
                        products.append(product)
                except Exception as e:
                    self.logger.debug(f"Error parsing product card {i}: {e}")

        except Exception as e:
            self.logger.error(f"Error loading category page: {e}")
        finally:
            await page.close()

        return products

    async def _parse_product_card(self, card, category_name: str) -> RawProduct | None:
        """Parse a single product card element."""
        try:
            # These selectors are approximate — will need adjustment
            # based on actual Esselunga DOM structure
            name = await card.locator('[data-testid="product-name"]').inner_text()
            if not name:
                return None

            # Price
            price_text = await card.locator('[data-testid="product-price"]').inner_text()
            price = self._parse_price(price_text)

            # Discounted price
            price_discounted = None
            discount_label = None
            try:
                promo = card.locator('[data-testid="product-promo"]')
                if await promo.is_visible(timeout=500):
                    discount_label = await promo.inner_text()
                    orig_price = card.locator('[data-testid="product-original-price"]')
                    if await orig_price.is_visible(timeout=500):
                        price_discounted = price
                        price = self._parse_price(await orig_price.inner_text())
            except Exception:
                pass

            # Image
            image_url = None
            try:
                img = card.locator('img').first
                image_url = await img.get_attribute('src')
            except Exception:
                pass

            # Link
            product_url = ""
            try:
                link = card.locator('a').first
                href = await link.get_attribute('href')
                if href:
                    product_url = f"https://www.esselunga.it{href}" if href.startswith('/') else href
            except Exception:
                pass

            # Quantity — often in the product name
            quantity_raw = ""
            qty_match = re.search(r'(\d+[,.]?\d*\s*(?:ml|l|lt|g|gr|kg|cl|pz|conf))', name, re.I)
            if qty_match:
                quantity_raw = qty_match.group(1)

            # Brand — often the first word(s) before the product type
            brand = None

            return RawProduct(
                external_id=product_url or name,
                name=name,
                brand=brand,
                price=price,
                price_discounted=price_discounted,
                discount_label=discount_label,
                quantity_raw=quantity_raw,
                image_url=image_url,
                product_url=product_url,
                category_raw=category_name,
                scraped_at=datetime.utcnow(),
            )
        except Exception as e:
            self.logger.debug(f"Failed to parse product card: {e}")
            return None

    def _parse_price(self, text: str) -> float:
        """Parse price string like '€ 2,49' or '2.49' to float."""
        cleaned = text.replace('€', '').replace(',', '.').strip()
        match = re.search(r'(\d+\.?\d*)', cleaned)
        if match:
            return float(match.group(1))
        return 0.0
