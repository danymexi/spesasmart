"""Penny Market online catalog scraper — sitemap-based product extraction.

Penny Italy uses Nuxt.js with SSR, which means product data is rendered
server-side in the HTML.  The sitemap at ``penny.it/sitemap.xml`` contains
~600 product URLs.

No headless browser needed — standard httpx + BeautifulSoup.

Strategy:
    1. Fetch sitemap from penny.it/sitemap.xml
    2. Filter for product URLs (pattern: /prodotti/ or /products/)
    3. Parse each SSR-rendered product page
    4. Save to DB via ProductMatcher for dedup
"""

from __future__ import annotations

import asyncio
import json
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

SITEMAP_URL = "https://www.penny.it/sitemap.xml"
BASE_URL = "https://www.penny.it"
REQUEST_DELAY = 1.5  # seconds between product page fetches
MAX_PRODUCTS = 800  # safety limit

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "it-IT,it;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class PennyOnlineScraper:
    """Scrapes the Penny Market Italy product catalog via sitemap + SSR pages."""

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
                logger.error("Chain 'penny' not found in DB.")
                return 0

            # Step 1: Fetch sitemap (may be a sitemap index)
            product_urls = await self._fetch_product_urls(client)
            if not product_urls:
                logger.warning("No product URLs found in Penny sitemap.")
                return 0

            logger.info(
                "Found %d product URLs in Penny sitemap.", len(product_urls)
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
                    logger.debug("Failed to parse Penny product: %s", url)

                if i > 0 and i % 50 == 0:
                    logger.info(
                        "Penny catalog progress: %d/%d URLs, %d saved.",
                        i, len(product_urls), saved,
                    )

                await asyncio.sleep(REQUEST_DELAY)

            logger.info(
                "Penny catalog scrape complete: %d products saved from %d URLs.",
                saved, len(product_urls),
            )
            return saved

    async def _fetch_product_urls(self, client: httpx.AsyncClient) -> list[str]:
        """Fetch sitemap(s) and extract product URLs."""
        resp = await client.get(SITEMAP_URL)
        resp.raise_for_status()

        root = ET.fromstring(resp.text)
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

        # Check if this is a sitemap index
        sub_sitemaps = root.findall(".//sm:sitemap/sm:loc", ns)
        if sub_sitemaps:
            # Fetch each sub-sitemap and collect product URLs
            urls = []
            for sitemap_el in sub_sitemaps:
                sitemap_url = (sitemap_el.text or "").strip()
                if not sitemap_url:
                    continue
                try:
                    sub_urls = await self._parse_sitemap(client, sitemap_url)
                    urls.extend(sub_urls)
                except Exception:
                    logger.debug("Failed to fetch sub-sitemap: %s", sitemap_url)
                await asyncio.sleep(0.5)
            return urls

        # Direct sitemap with URLs
        return self._filter_product_urls(root, ns)

    async def _parse_sitemap(
        self, client: httpx.AsyncClient, url: str
    ) -> list[str]:
        """Parse a single sitemap XML and return product URLs."""
        resp = await client.get(url)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        return self._filter_product_urls(root, ns)

    @staticmethod
    def _filter_product_urls(root: ET.Element, ns: dict) -> list[str]:
        """Extract URLs that look like product pages."""
        urls = []
        for url_el in root.findall(".//sm:url/sm:loc", ns):
            url = (url_el.text or "").strip()
            if url and ("/prodotti/" in url or "/products/" in url or "/offerte/" in url):
                urls.append(url)
        return urls

    async def _parse_product_page(
        self, client: httpx.AsyncClient, url: str
    ) -> dict[str, Any] | None:
        """Fetch an SSR product page and extract structured data."""
        resp = await client.get(url)
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        # Try JSON-LD first (Nuxt.js often includes it)
        product_data = self._extract_from_jsonld(soup)
        if product_data:
            product_data["source_url"] = url
            return product_data

        # Fallback: parse HTML elements
        name_el = soup.find("h1")
        if not name_el:
            return None
        name = name_el.get_text(strip=True)
        if not name or len(name) < 2:
            return None

        price = self._extract_price_from_html(soup)
        image_url = self._extract_meta(soup, "og:image")
        category = self._extract_category(soup)

        return {
            "name": name,
            "brand": None,
            "category": category,
            "price": price,
            "image_url": image_url,
            "source_url": url,
        }

    def _extract_from_jsonld(self, soup: BeautifulSoup) -> dict[str, Any] | None:
        """Extract product data from JSON-LD structured data."""
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                if isinstance(data, list):
                    data = next(
                        (d for d in data if d.get("@type") == "Product"), None
                    )
                if not isinstance(data, dict) or data.get("@type") != "Product":
                    continue

                name = (data.get("name") or "").strip()
                if not name:
                    continue

                # Price
                price = None
                offers = data.get("offers", {})
                if isinstance(offers, list):
                    offers = offers[0] if offers else {}
                raw_price = offers.get("price")
                if raw_price:
                    try:
                        price = Decimal(str(raw_price))
                    except InvalidOperation:
                        pass

                return {
                    "name": name,
                    "brand": (data.get("brand", {}).get("name") or "").strip() or None,
                    "category": (data.get("category") or "").strip() or None,
                    "price": price,
                    "image_url": data.get("image"),
                    "barcode": (data.get("gtin13") or data.get("sku") or "").strip() or None,
                }
            except (json.JSONDecodeError, TypeError, AttributeError):
                continue
        return None

    @staticmethod
    def _extract_price_from_html(soup: BeautifulSoup) -> Decimal | None:
        """Extract price from HTML elements."""
        # Common patterns: <span class="price">1,99 €</span>
        for el in soup.find_all(attrs={"class": re.compile(r"price", re.I)}):
            text = el.get_text(strip=True)
            match = re.search(r"(\d+[.,]\d{2})", text)
            if match:
                try:
                    return Decimal(match.group(1).replace(",", "."))
                except InvalidOperation:
                    continue
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
    def _extract_category(soup: BeautifulSoup) -> str | None:
        """Extract category from breadcrumb navigation."""
        breadcrumbs = soup.find("nav", attrs={"aria-label": re.compile(r"breadcrumb", re.I)})
        if breadcrumbs:
            items = breadcrumbs.find_all("a")
            cats = [a.get_text(strip=True) for a in items if a.get_text(strip=True).lower() != "home"]
            if cats:
                return cats[-1][:100]
        return None

    async def _get_chain_id(self) -> uuid.UUID | None:
        """Resolve the Penny chain ID from DB."""
        async with async_session() as session:
            result = await session.execute(
                select(Chain).where(Chain.slug == "penny")
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
                        "source": "penny_online",
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
                        confidence=Decimal("0.85"),
                    )
                    session.add(offer)

                await session.commit()
                return True
            except Exception:
                logger.debug("Failed to save Penny product: %s", data.get("name"))
                return False
