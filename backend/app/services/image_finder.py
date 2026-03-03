"""Product image finder service.

Searches for product images using:
  1. Open Food Facts (free API, reliable)
  2. Google Image Search (fallback)

Tracks search attempts via `image_searched_at` to avoid re-searching
products that have already been tried recently.
"""

import asyncio
import logging
import re
from difflib import SequenceMatcher

import httpx
from sqlalchemy import select, func, or_, text
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

# Minimum similarity ratio (0-1) for Open Food Facts name matching
OFF_MIN_SIMILARITY = 0.45


async def _check_url(url: str, client: httpx.AsyncClient) -> bool:
    """Check if an image URL is reachable (returns 200)."""
    try:
        r = await client.head(url, follow_redirects=True, timeout=8.0)
        return r.status_code == 200
    except Exception:
        return False


async def _search_off(
    product_name: str, brand: str | None, client: httpx.AsyncClient
) -> str | None:
    """Search Open Food Facts for a product image.

    Returns the image URL if a good match is found, None otherwise.
    """
    search_terms = product_name
    if brand:
        search_terms = f"{brand} {product_name}"

    try:
        r = await client.get(
            "https://world.openfoodfacts.org/cgi/search.pl",
            params={
                "search_terms": search_terms,
                "json": "1",
                "page_size": "5",
                "fields": "product_name,image_url,brands",
            },
            timeout=10.0,
        )
        if r.status_code != 200:
            return None

        data = r.json()
        products = data.get("products", [])

        for p in products:
            off_name = (p.get("product_name") or "").lower()
            off_brands = (p.get("brands") or "").lower()
            image_url = p.get("image_url")

            if not image_url:
                continue

            # Check name similarity
            target = product_name.lower()
            ratio = SequenceMatcher(None, target, off_name).ratio()

            # Boost similarity if brand matches
            if brand and brand.lower() in off_brands:
                ratio += 0.15

            if ratio >= OFF_MIN_SIMILARITY:
                logger.debug(
                    "OFF match for %r: %r (ratio=%.2f)", product_name, off_name, ratio
                )
                return image_url

    except Exception as e:
        logger.warning("Open Food Facts search failed for %r: %s", product_name, e)

    return None


async def _search_google(query: str, client: httpx.AsyncClient) -> str | None:
    """Search Google Images and return the first valid product image URL."""
    try:
        r = await client.get(
            "https://www.google.com/search",
            params={"q": query, "tbm": "isch", "hl": "it"},
            headers=HEADERS,
            timeout=10.0,
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
        logger.warning("Google image search failed for %r: %s", query, e)

    return None


class ProductImageFinder:
    """Find and update images for products missing or broken image_url."""

    async def backfill(
        self, session: AsyncSession, limit: int = 50
    ) -> int:
        """Find images for products without or with broken image_url.

        Skips products searched in the last 7 days (via image_searched_at).
        """
        seven_days_ago = text("now() - interval '7 days'")

        # Products with no image and not recently searched
        result = await session.execute(
            select(Product)
            .where(
                Product.image_url.is_(None),
                or_(
                    Product.image_searched_at.is_(None),
                    Product.image_searched_at < seven_days_ago,
                ),
            )
            .order_by(func.random())
            .limit(limit)
        )
        products_no_img = list(result.scalars().all())

        # Products with known broken domains
        remaining = limit - len(products_no_img)
        products_broken: list[Product] = []
        if remaining > 0 and BROKEN_DOMAINS:
            conditions = [
                Product.image_url.ilike(f"%{d}%") for d in BROKEN_DOMAINS
            ]
            result = await session.execute(
                select(Product)
                .where(
                    or_(*conditions),
                    or_(
                        Product.image_searched_at.is_(None),
                        Product.image_searched_at < seven_days_ago,
                    ),
                )
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
        async with httpx.AsyncClient(follow_redirects=True) as client:
            for idx, product in enumerate(products, 1):
                image_url = await self._find_image(product, client)

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

                # Mark search attempt regardless of result
                product.image_searched_at = func.now()

                # Progress log every 10 products
                if idx % 10 == 0:
                    logger.info(
                        "Image backfill progress: %d/%d searched, %d found.",
                        idx, len(products), updated,
                    )

                # Rate limit between searches
                await asyncio.sleep(1.5)

        await session.commit()

        logger.info(
            "Image backfill: %d/%d products updated.", updated, len(products)
        )
        return updated

    async def _find_image(
        self, product: Product, client: httpx.AsyncClient
    ) -> str | None:
        """Try sources in order: Open Food Facts, then Google."""

        # 1. Open Food Facts (primary — free, reliable)
        url = await _search_off(product.name, product.brand, client)
        if url and await _check_url(url, client):
            logger.debug("Image from OFF for %s", product.name)
            return url

        # 2. Google Images — try brand+name first, then name only
        queries = self._build_google_queries(product)
        for query in queries:
            url = await _search_google(query, client)
            if url and await _check_url(url, client):
                logger.debug("Image from Google for %s (query=%r)", product.name, query)
                return url
            # Rate limit between Google queries
            await asyncio.sleep(2.0)

        return None

    def _build_google_queries(self, product: Product) -> list[str]:
        """Build ordered list of Google search queries for a product."""
        queries = []
        if product.brand:
            queries.append(f"{product.brand} {product.name} supermercato")
        queries.append(f"{product.name} prodotto")
        return queries
