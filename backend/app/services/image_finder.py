"""Product image finder service.

Searches for product images using:
  1. Claude Haiku to generate optimized search queries (batch)
  2. Open Food Facts (free API, reliable)
  3. Google Image Search (fallback)

Tracks search attempts via `image_searched_at` to avoid re-searching
products that have already been tried recently.
"""

import asyncio
import json
import logging
import os
import re
from difflib import SequenceMatcher

import httpx
from sqlalchemy import select, func, or_, text, update
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
OFF_MIN_SIMILARITY = 0.40

# Claude batch size for query generation
CLAUDE_BATCH_SIZE = 40

CLAUDE_SYSTEM_PROMPT = """\
Sei un assistente che genera query di ricerca per trovare immagini di prodotti \
da supermercato italiano.

Riceverai una lista JSON di prodotti con "idx", "name" e "brand".
Per ciascuno restituisci un oggetto con:
- "idx": lo stesso indice ricevuto
- "off_query": query ottimizzata per Open Food Facts (brand + nome pulito del \
prodotto, senza quantita/peso/pezzi). Esempio: "Mulino Bianco Fette Biscottate"
- "google_query": query per Google Images (brand + prodotto + "prodotto \
supermercato"). Esempio: "Mulino Bianco Fette Biscottate prodotto supermercato"

Regole:
- Rimuovi quantita, pesi, formati (es. "500g", "6x1.5L", "12 pz")
- Mantieni il brand se presente
- Se il nome e' criptico o troncato, ricostruisci il nome piu probabile
- Restituisci SOLO un JSON array valido, nessun commento"""


async def _check_url(url: str, client: httpx.AsyncClient) -> bool:
    """Check if an image URL is reachable (returns 200)."""
    try:
        r = await client.head(url, follow_redirects=True, timeout=8.0)
        return r.status_code == 200
    except Exception:
        return False


async def _search_off(
    query: str, client: httpx.AsyncClient
) -> str | None:
    """Search Open Food Facts for a product image."""
    try:
        r = await client.get(
            "https://world.openfoodfacts.org/cgi/search.pl",
            params={
                "search_terms": query,
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

        target = query.lower()
        for p in products:
            off_name = (p.get("product_name") or "").lower()
            off_brands = (p.get("brands") or "").lower()
            image_url = p.get("image_url")

            if not image_url:
                continue

            ratio = SequenceMatcher(None, target, off_name).ratio()
            # Boost if brands overlap
            if any(w in off_brands for w in target.split() if len(w) > 3):
                ratio += 0.15

            if ratio >= OFF_MIN_SIMILARITY:
                logger.debug(
                    "OFF match for %r: %r (ratio=%.2f)", query, off_name, ratio
                )
                return image_url

    except Exception as e:
        logger.warning("Open Food Facts search failed for %r: %s", query, e)

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


async def _generate_queries_batch(
    products: list[Product],
    api_key: str,
) -> dict[str, dict]:
    """Use Claude Haiku to generate optimized search queries in batch.

    Returns a dict mapping product.id (str) -> {"off_query": ..., "google_query": ...}
    """
    import anthropic

    payload = []
    idx_to_id: dict[int, str] = {}
    for i, p in enumerate(products):
        payload.append({
            "idx": i,
            "name": p.name,
            "brand": p.brand or "",
        })
        idx_to_id[i] = str(p.id)

    client = anthropic.AsyncAnthropic(api_key=api_key)
    result_map: dict[str, dict] = {}

    try:
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            system=CLAUDE_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False),
            }],
        )
        raw = response.content[0].text

        # Parse JSON (strip markdown fences if present)
        try:
            items = json.loads(raw)
        except json.JSONDecodeError:
            cleaned = raw
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("```", 1)[0]
            items = json.loads(cleaned.strip())

        for item in items:
            idx = item.get("idx")
            if idx is not None and idx in idx_to_id:
                pid = idx_to_id[idx]
                result_map[pid] = {
                    "off_query": item.get("off_query", ""),
                    "google_query": item.get("google_query", ""),
                }

        logger.info(
            "Claude generated queries for %d/%d products.",
            len(result_map), len(products),
        )

    except Exception as e:
        logger.warning("Claude query generation failed: %s", e)
        # Fallback: use raw product name + brand
        for p in products:
            pid = str(p.id)
            name = p.name
            brand = p.brand or ""
            result_map[pid] = {
                "off_query": f"{brand} {name}".strip(),
                "google_query": f"{brand} {name} prodotto supermercato".strip(),
            }

    return result_map


class ProductImageFinder:
    """Find and update images for products missing or broken image_url."""

    def __init__(self, anthropic_api_key: str | None = None):
        self.anthropic_api_key = anthropic_api_key

    async def backfill(
        self, session: AsyncSession, limit: int = 50
    ) -> int:
        """Find images for products without or with broken image_url.

        Skips products searched in the last 7 days (via image_searched_at).
        """
        seven_days_ago = text("now() - interval '7 days'")

        # Phase 0: Null out known broken domain URLs so they appear as "no image"
        for domain in BROKEN_DOMAINS:
            await session.execute(
                update(Product)
                .where(Product.image_url.ilike(f"%{domain}%"))
                .values(image_url=None, image_searched_at=None)
            )
        await session.flush()

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
        products = list(result.scalars().all())

        if not products:
            logger.info("No products needing images found.")
            return 0

        logger.info("Found %d products to search images for.", len(products))

        # Phase 1: Generate optimized search queries via Claude (in batches)
        query_map: dict[str, dict] = {}
        if self.anthropic_api_key:
            for batch_start in range(0, len(products), CLAUDE_BATCH_SIZE):
                batch = products[batch_start:batch_start + CLAUDE_BATCH_SIZE]
                batch_queries = await _generate_queries_batch(
                    batch, self.anthropic_api_key
                )
                query_map.update(batch_queries)
                if batch_start + CLAUDE_BATCH_SIZE < len(products):
                    await asyncio.sleep(1.0)
        else:
            # No Claude key: fallback to simple queries
            for p in products:
                pid = str(p.id)
                brand = p.brand or ""
                query_map[pid] = {
                    "off_query": f"{brand} {p.name}".strip(),
                    "google_query": f"{brand} {p.name} prodotto supermercato".strip(),
                }

        # Phase 2: Search for images using the generated queries
        updated = 0
        async with httpx.AsyncClient(follow_redirects=True) as client:
            for idx, product in enumerate(products, 1):
                pid = str(product.id)
                queries = query_map.get(pid, {})
                off_q = queries.get("off_query", product.name)
                google_q = queries.get("google_query", f"{product.name} prodotto")

                image_url = await self._find_image(
                    product, off_q, google_q, client
                )

                if image_url:
                    product.image_url = image_url
                    updated += 1
                    logger.info(
                        "[%d/%d] Found image for %s (%s): %s",
                        idx, len(products),
                        product.name[:50], product.brand, image_url[:80],
                    )
                else:
                    logger.debug(
                        "[%d/%d] No image for %s (%s)",
                        idx, len(products),
                        product.name[:50], product.brand,
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
                await asyncio.sleep(1.0)

        await session.commit()

        logger.info(
            "Image backfill complete: %d/%d products updated.", updated, len(products)
        )
        return updated

    async def _find_image(
        self,
        product: Product,
        off_query: str,
        google_query: str,
        client: httpx.AsyncClient,
    ) -> str | None:
        """Try sources in order: Open Food Facts, then Google."""

        # 1. Open Food Facts with Claude-optimized query
        url = await _search_off(off_query, client)
        if url and await _check_url(url, client):
            return url

        # 2. Google Images with Claude-optimized query
        url = await _search_google(google_query, client)
        if url and await _check_url(url, client):
            return url
        await asyncio.sleep(1.5)

        # 3. Google fallback: try just product name
        if google_query != f"{product.name} prodotto":
            url = await _search_google(f"{product.name} prodotto", client)
            if url and await _check_url(url, client):
                return url

        return None
