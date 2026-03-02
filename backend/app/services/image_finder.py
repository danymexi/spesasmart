"""Product image finder service.

Searches for product images via Google Image Search for products
that have no image_url or a broken (404) image_url. Runs as a background job.
"""

import asyncio
import logging
import re
from typing import Sequence

import httpx
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Product

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
}

# Patterns for image URLs in Google's HTML response
IMG_URL_RE = re.compile(
    r'\["(https://[^"]+\.(?:jpg|jpeg|png|webp)(?:\?[^"]*)?)"',
)

# Skip images from these domains (logos, icons, not product images)
SKIP_DOMAINS = {
    "google.com", "gstatic.com", "googleapis.com",
    "facebook.com", "instagram.com", "twitter.com",
    "wikipedia.org", "wikimedia.org",
}

# Domains known to return 404 for most product images
BROKEN_DOMAINS = {
    "images.services.esselunga.it",
}


async def _search_image(query: str, client: httpx.AsyncClient) -> str | None:
    """Search Google Images and return the first product image URL."""
    try:
        r = await client.get(
            "https://www.google.com/search",
            params={"q": query, "tbm": "isch", "hl": "it"},
            headers=HEADERS,
        )
        if r.status_code != 200:
            return None

        urls = IMG_URL_RE.findall(r.text)
        for url in urls:
            domain = url.split("/")[2].lower()
            if any(skip in domain for skip in SKIP_DOMAINS):
                continue
            if domain in BROKEN_DOMAINS:
                continue
            return url

    except Exception as e:
        logger.warning("Image search failed for %r: %s", query, e)

    return None


async def _check_url(url: str, client: httpx.AsyncClient) -> bool:
    """Check if an image URL is reachable (returns 200)."""
    try:
        r = await client.head(url, follow_redirects=True)
        return r.status_code == 200
    except Exception:
        return False


class ProductImageFinder:
    """Find and update images for products missing or broken image_url."""

    async def backfill(
        self, session: AsyncSession, limit: int = 50
    ) -> int:
        """Find images for products without or with broken image_url."""
        # First: products with no image
        result = await session.execute(
            select(Product)
            .where(Product.image_url.is_(None))
            .order_by(func.random())
            .limit(limit)
        )
        products_no_img = list(result.scalars().all())

        # Second: products with known broken domains
        remaining = limit - len(products_no_img)
        products_broken: list[Product] = []
        if remaining > 0 and BROKEN_DOMAINS:
            conditions = [
                Product.image_url.ilike(f"%{d}%") for d in BROKEN_DOMAINS
            ]
            result = await session.execute(
                select(Product)
                .where(or_(*conditions))
                .order_by(func.random())
                .limit(remaining)
            )
            products_broken = list(result.scalars().all())

        products = products_no_img + products_broken
        if not products:
            logger.info("No products needing images found.")
            return 0

        logger.info(
            "Found %d products to fix (%d no image, %d broken URL).",
            len(products), len(products_no_img), len(products_broken),
        )

        updated = 0
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            for idx, product in enumerate(products, 1):
                query = self._build_query(product)
                image_url = await _search_image(query, client)

                if image_url:
                    product.image_url = image_url
                    updated += 1
                    logger.info(
                        "Found image for %s (%s): %s",
                        product.name, product.brand, image_url[:80],
                    )
                else:
                    logger.debug(
                        "No image found for %s (%s)",
                        product.name, product.brand,
                    )

                # Progress log every 10 products
                if idx % 10 == 0:
                    logger.info(
                        "Image backfill progress: %d/%d searched, %d found.",
                        idx, len(products), updated,
                    )

                # Rate limit: wait between Google searches to avoid bans
                await asyncio.sleep(2.0)

        if updated:
            await session.commit()

        logger.info(
            "Image backfill: %d/%d products updated.", updated, len(products)
        )
        return updated

    def _build_query(self, product: Product) -> str:
        """Build a search query for a product."""
        parts = []
        if product.brand:
            parts.append(product.brand)
        parts.append(product.name)
        parts.append("prodotto")
        return " ".join(parts)
