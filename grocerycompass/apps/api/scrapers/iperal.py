"""Iperal scraper using Playwright."""

import re
import logging
from datetime import datetime
from typing import AsyncIterator

from scrapers.base import BaseSupermarketScraper, RawProduct
from scrapers.browser import get_stealth_browser, close_browser

logger = logging.getLogger(__name__)

IPERAL_CATEGORIES = [
    {"name": "Frutta e Verdura", "url": "/reparto/frutta-e-verdura"},
    {"name": "Carne e Salumi", "url": "/reparto/carne-e-salumi"},
    {"name": "Pesce", "url": "/reparto/pesce"},
    {"name": "Latticini", "url": "/reparto/latticini"},
    {"name": "Pane e Dolci", "url": "/reparto/pane-e-dolci"},
    {"name": "Pasta e Riso", "url": "/reparto/pasta-e-riso"},
    {"name": "Conserve", "url": "/reparto/conserve"},
    {"name": "Bevande", "url": "/reparto/bevande"},
    {"name": "Surgelati", "url": "/reparto/surgelati"},
    {"name": "Igiene Persona", "url": "/reparto/igiene-persona"},
    {"name": "Pulizia Casa", "url": "/reparto/pulizia-casa"},
]

BASE_URL = "https://www.iperalonline.it"


class IperalScraper(BaseSupermarketScraper):
    CHAIN_SLUG = "iperal"
    RATE_LIMIT_DELAY = 2.5

    async def scrape_all_products(self) -> AsyncIterator[RawProduct]:
        """Scrape all products from Iperal."""
        playwright, browser, context = await get_stealth_browser()

        try:
            for category in IPERAL_CATEGORIES:
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
        """Scrape products from a category page."""
        page = await context.new_page()
        products = []

        try:
            url = f"{BASE_URL}{category_path}"
            await page.goto(url, wait_until="networkidle", timeout=30000)

            # Handle cookie consent
            try:
                cookie_btn = page.locator('button:has-text("Accetta")')
                if await cookie_btn.is_visible(timeout=3000):
                    await cookie_btn.click()
            except Exception:
                pass

            # Pagination: load all pages
            page_num = 1
            while True:
                # Get product cards on current page
                product_cards = page.locator('.product-card, .product-item, [class*="product"]')
                count = await product_cards.count()
                self.logger.info(f"Page {page_num}: found {count} products in {category_name}")

                for i in range(count):
                    try:
                        card = product_cards.nth(i)
                        product = await self._parse_product_card(card, category_name)
                        if product and product.price > 0:
                            products.append(product)
                    except Exception as e:
                        self.logger.debug(f"Error parsing card {i}: {e}")

                # Check for next page
                next_btn = page.locator('[class*="next"], a:has-text("Successiva")')
                if await next_btn.count() > 0 and await next_btn.first.is_visible():
                    await next_btn.first.click()
                    await page.wait_for_load_state("networkidle")
                    page_num += 1
                    await self.rate_limit()
                else:
                    break

        except Exception as e:
            self.logger.error(f"Error loading category {category_name}: {e}")
        finally:
            await page.close()

        return products

    async def _parse_product_card(self, card, category_name: str) -> RawProduct | None:
        """Parse a product card."""
        try:
            # Get product name
            name_el = card.locator('.product-name, .product-title, h3, h4').first
            name = await name_el.inner_text() if await name_el.count() > 0 else ""
            if not name:
                return None

            # Get price
            price_el = card.locator('.price, .product-price, [class*="price"]').first
            price_text = await price_el.inner_text() if await price_el.count() > 0 else "0"
            price = self._parse_price(price_text)

            # Promo/discount
            price_discounted = None
            discount_label = None
            try:
                promo_el = card.locator('.promo, .discount, [class*="promo"]')
                if await promo_el.count() > 0:
                    discount_label = await promo_el.first.inner_text()
                    orig_el = card.locator('.original-price, .old-price, [class*="original"]')
                    if await orig_el.count() > 0:
                        price_discounted = price
                        price = self._parse_price(await orig_el.first.inner_text())
            except Exception:
                pass

            # Image
            image_url = None
            try:
                img = card.locator('img').first
                if await img.count() > 0:
                    image_url = await img.get_attribute('src')
            except Exception:
                pass

            # Link
            product_url = ""
            try:
                link = card.locator('a').first
                if await link.count() > 0:
                    href = await link.get_attribute('href')
                    if href:
                        product_url = f"{BASE_URL}{href}" if href.startswith('/') else href
            except Exception:
                pass

            # Quantity from name
            quantity_raw = ""
            qty_match = re.search(r'(\d+[,.]?\d*\s*(?:ml|l|lt|g|gr|kg|cl|pz|conf))', name, re.I)
            if qty_match:
                quantity_raw = qty_match.group(1)

            return RawProduct(
                external_id=product_url or name,
                name=name,
                price=price,
                price_discounted=price_discounted,
                discount_label=discount_label,
                quantity_raw=quantity_raw,
                image_url=image_url,
                product_url=product_url,
                category_raw=category_name,
                scraped_at=datetime.utcnow(),
            )
        except Exception:
            return None

    def _parse_price(self, text: str) -> float:
        """Parse price string to float."""
        cleaned = text.replace('€', '').replace(',', '.').strip()
        match = re.search(r'(\d+\.?\d*)', cleaned)
        return float(match.group(1)) if match else 0.0
