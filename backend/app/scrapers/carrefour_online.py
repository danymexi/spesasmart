"""Carrefour online catalog scraper — sitemap-based product extraction.

Carrefour Italy uses Salesforce Commerce Cloud.  The product sitemap at
``carrefour.it/sitemap_0-product.xml`` contains ~1,100 product URLs with
EAN codes embedded in the URL path.

Each product page includes structured data (name, brand, price, category,
image) in standard HTML — no JavaScript rendering needed.

Strategy:
    1. Fetch product sitemap XML
    2. Parse product URLs (EAN codes in URL path)
    3. Fetch each product page and extract structured data
    4. Save to DB via ProductMatcher for dedup
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select

from app.database import async_session
from app.models.chain import Chain
from app.models.offer import Offer
from app.services.product_matcher import ProductMatcher

logger = logging.getLogger(__name__)

SITEMAP_URL = "https://www.carrefour.it/sitemap_0-product.xml"
BASE_URL = "https://www.carrefour.it"
REQUEST_DELAY = 1.5  # seconds between product page fetches
MAX_PRODUCTS = 1200  # safety limit

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "it-IT,it;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class CarrefourOnlineScraper:
    """Scrapes the Carrefour Italy product catalog via sitemap + page parsing."""

    def __init__(self) -> None:
        self._matcher = ProductMatcher()
        self._chain_id: uuid.UUID | None = None

    async def scrape(self) -> int:
        """Run the full catalog scrape.  Returns the number of products saved."""
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
            headers=_HEADERS,
        ) as client:
            # Resolve chain
            self._chain_id = await self._get_chain_id()
            if not self._chain_id:
                logger.error("Chain 'carrefour' not found in DB.")
                return 0

            # Step 1: Fetch sitemap
            product_urls = await self._fetch_sitemap(client)
            if not product_urls:
                logger.warning("No product URLs found in Carrefour sitemap.")
                return 0

            logger.info(
                "Found %d product URLs in Carrefour sitemap.", len(product_urls)
            )

            # Step 2: Fetch and parse product pages
            saved = 0
            for i, url in enumerate(product_urls[:MAX_PRODUCTS]):
                try:
                    product_data = await self._parse_product_page(client, url)
                    if product_data:
                        ok = await self._save_product(product_data)
                        if ok:
                            saved += 1
                except Exception:
                    logger.debug("Failed to parse product: %s", url)

                if i > 0 and i % 50 == 0:
                    logger.info(
                        "Carrefour catalog progress: %d/%d URLs, %d saved.",
                        i, len(product_urls), saved,
                    )

                await asyncio.sleep(REQUEST_DELAY)

            logger.info(
                "Carrefour catalog scrape complete: %d products saved from %d URLs.",
                saved, len(product_urls),
            )
            return saved

    async def _fetch_sitemap(self, client: httpx.AsyncClient) -> list[str]:
        """Fetch and parse the product sitemap XML."""
        resp = await client.get(SITEMAP_URL)
        resp.raise_for_status()

        root = ET.fromstring(resp.text)
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

        urls = []
        for url_el in root.findall(".//sm:url/sm:loc", ns):
            url = (url_el.text or "").strip()
            if url and "/p/" in url:
                urls.append(url)

        return urls

    async def _parse_product_page(
        self, client: httpx.AsyncClient, url: str
    ) -> dict[str, Any] | None:
        """Fetch a product page and extract structured data."""
        resp = await client.get(url)
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        # Extract product name
        name_el = soup.find("h1")
        if not name_el:
            return None
        name = name_el.get_text(strip=True)
        if not name or len(name) < 2:
            return None

        # Extract price from JSON-LD or meta tags
        price = self._extract_price(soup)

        # Extract brand
        brand = self._extract_meta(soup, "og:brand") or self._extract_brand_from_page(soup)

        # Extract EAN from URL
        ean = self._extract_ean_from_url(url)

        # Extract image
        image_url = self._extract_meta(soup, "og:image")

        # Extract category from breadcrumbs
        category = self._extract_category(soup)

        return {
            "name": name,
            "brand": brand,
            "category": category,
            "price": price,
            "barcode": ean,
            "image_url": image_url,
            "source_url": url,
        }

    def _extract_price(self, soup: BeautifulSoup) -> Decimal | None:
        """Extract price from JSON-LD structured data or meta tags."""
        import json

        # Try JSON-LD
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                if isinstance(data, dict):
                    offers = data.get("offers", {})
                    if isinstance(offers, list):
                        offers = offers[0] if offers else {}
                    raw = offers.get("price")
                    if raw:
                        return Decimal(str(raw))
            except (json.JSONDecodeError, InvalidOperation, IndexError, KeyError):
                continue

        # Try meta product:price:amount
        meta = soup.find("meta", attrs={"property": "product:price:amount"})
        if meta:
            try:
                return Decimal(meta.get("content", ""))
            except InvalidOperation:
                pass

        return None

    @staticmethod
    def _extract_meta(soup: BeautifulSoup, prop: str) -> str | None:
        """Extract content from an Open Graph meta tag."""
        tag = soup.find("meta", attrs={"property": prop})
        if tag:
            val = (tag.get("content") or "").strip()
            return val if val else None
        return None

    @staticmethod
    def _extract_brand_from_page(soup: BeautifulSoup) -> str | None:
        """Try to extract brand from page elements."""
        # Common pattern: <span class="...brand...">BrandName</span>
        for el in soup.find_all(attrs={"class": re.compile(r"brand", re.I)}):
            text = el.get_text(strip=True)
            if text and len(text) < 80:
                return text
        return None

    @staticmethod
    def _extract_ean_from_url(url: str) -> str | None:
        """Extract EAN/barcode from the product URL path."""
        # Pattern: /p/XXXXXXXXX or /p-XXXXXXXXX (13-digit EAN)
        match = re.search(r"/p[/-](\d{8,13})", url)
        return match.group(1) if match else None

    @staticmethod
    def _extract_category(soup: BeautifulSoup) -> str | None:
        """Extract category from breadcrumb navigation."""
        breadcrumbs = soup.find("nav", attrs={"aria-label": re.compile(r"breadcrumb", re.I)})
        if breadcrumbs:
            items = breadcrumbs.find_all("a")
            # Skip "Home", take the last meaningful category
            cats = [a.get_text(strip=True) for a in items if a.get_text(strip=True).lower() != "home"]
            if cats:
                return cats[-1][:100]
        return None

    async def _get_chain_id(self) -> uuid.UUID | None:
        """Resolve the Carrefour chain ID from DB."""
        async with async_session() as session:
            result = await session.execute(
                select(Chain).where(Chain.slug == "carrefour")
            )
            chain = result.scalar_one_or_none()
            return chain.id if chain else None

    async def _save_product(self, data: dict[str, Any]) -> bool:
        """Save a product to the DB using ProductMatcher for dedup."""
        async with async_session() as session:
            try:
                product = await self._matcher.create_or_match_product(
                    {
                        "name": data["name"],
                        "brand": data.get("brand"),
                        "category": data.get("category"),
                        "barcode": data.get("barcode"),
                        "image_url": data.get("image_url"),
                        "source": "carrefour_online",
                    },
                    session=session,
                )

                # If we have a price, create an offer too
                if data.get("price"):
                    today = date.today()
                    offer = Offer(
                        product_id=product.id,
                        chain_id=self._chain_id,
                        original_price=None,
                        offer_price=data["price"],
                        valid_from=today,
                        valid_to=today + timedelta(days=7),
                        raw_text=data.get("name", "")[:500],
                        confidence=Decimal("0.90"),
                    )
                    session.add(offer)

                await session.commit()
                return True
            except Exception:
                logger.debug("Failed to save Carrefour product: %s", data.get("name"))
                return False
