"""One-time script to deduplicate products in the database.

Finds cross-source duplicates (Iperal vs Esselunga with different naming)
using the improved ProductMatcher and merges them by:
  1. Keeping the product with the most data (image, category, unit)
  2. Updating offers and watchlist entries to point to the kept product
  3. Deleting the duplicate

Run from the backend directory:
    PYTHONPATH=. python scripts/dedup_products.py
"""

import asyncio
import logging
import sys
from collections import defaultdict

from sqlalchemy import select, update, delete, func

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


async def main():
    from app.database import async_session
    from app.models import Product
    from app.models.offer import Offer
    from app.models.user import UserWatchlist
    from app.services.product_matcher import ProductMatcher

    pm = ProductMatcher()

    async with async_session() as session:
        # Load all products
        result = await session.execute(select(Product))
        all_products = list(result.scalars().all())
        logger.info("Loaded %d products.", len(all_products))

        # Group by canonical brand for efficient comparison
        by_brand: dict[str | None, list[Product]] = defaultdict(list)
        for p in all_products:
            by_brand[p.brand].append(p)

        merge_pairs: list[tuple[Product, Product]] = []  # (keep, delete)
        seen_ids = set()

        for brand, products in by_brand.items():
            if len(products) < 2:
                continue

            # Sort by amount of data (descending) so the "richer" product
            # comes first in comparisons
            products.sort(key=lambda p: _richness(p), reverse=True)

            for i, p1 in enumerate(products):
                if p1.id in seen_ids:
                    continue
                for j in range(i + 1, len(products)):
                    p2 = products[j]
                    if p2.id in seen_ids:
                        continue
                    # Skip within-source duplicates (they have barcodes)
                    if p1.source and p2.source and p1.source == p2.source:
                        continue

                    score = pm.fuzzy_match(
                        p1.name, p2.name,
                        brand1=p1.brand, brand2=p2.brand,
                    )

                    cb1 = pm.normalize_brand(p1.brand)
                    cb2 = pm.normalize_brand(p2.brand)
                    threshold = 80 if cb1 and cb2 and cb1 == cb2 else 85

                    if score >= threshold:
                        # Keep p1 (richer), delete p2
                        merge_pairs.append((p1, p2))
                        seen_ids.add(p2.id)

        logger.info("Found %d duplicate pairs to merge.", len(merge_pairs))

        if not merge_pairs:
            logger.info("No duplicates found. Exiting.")
            return

        # Confirm
        for keep, dup in merge_pairs[:20]:
            logger.info(
                "  MERGE: [%s] '%s' (%s) <- [%s] '%s' (%s)",
                keep.source, keep.name[:40], keep.brand,
                dup.source, dup.name[:40], dup.brand,
            )
        if len(merge_pairs) > 20:
            logger.info("  ... and %d more.", len(merge_pairs) - 20)

        if "--dry-run" in sys.argv:
            logger.info("Dry run — no changes made.")
            return

        # Execute merges
        merged = 0
        for keep, dup in merge_pairs:
            try:
                # Update offers to point to the kept product
                await session.execute(
                    update(Offer)
                    .where(Offer.product_id == dup.id)
                    .values(product_id=keep.id)
                )

                # Update watchlist entries — handle unique constraint
                # (user might have both products in watchlist)
                existing_wl = await session.execute(
                    select(UserWatchlist.user_id)
                    .where(UserWatchlist.product_id == keep.id)
                )
                existing_user_ids = {row[0] for row in existing_wl.fetchall()}

                # Delete watchlist entries that would conflict
                if existing_user_ids:
                    await session.execute(
                        delete(UserWatchlist)
                        .where(
                            UserWatchlist.product_id == dup.id,
                            UserWatchlist.user_id.in_(existing_user_ids),
                        )
                    )

                # Update remaining watchlist entries
                await session.execute(
                    update(UserWatchlist)
                    .where(UserWatchlist.product_id == dup.id)
                    .values(product_id=keep.id)
                )

                # Enrich the kept product with data from the duplicate
                if not keep.image_url and dup.image_url:
                    keep.image_url = dup.image_url
                if (not keep.category or keep.category == "Supermercato") and dup.category:
                    keep.category = dup.category
                if not keep.subcategory and dup.subcategory:
                    keep.subcategory = dup.subcategory
                if not keep.unit and dup.unit:
                    keep.unit = dup.unit

                # Delete the duplicate product
                await session.execute(
                    delete(Product).where(Product.id == dup.id)
                )

                merged += 1
            except Exception:
                logger.exception(
                    "Failed to merge %s -> %s", dup.id, keep.id
                )
                await session.rollback()
                return

        await session.commit()
        logger.info("Successfully merged %d duplicate products.", merged)

        # Final stats
        result = await session.execute(
            select(Product.source, func.count()).group_by(Product.source)
        )
        logger.info("Products by source after cleanup:")
        for source, count in result.fetchall():
            logger.info("  %s: %d", source, count)


def _richness(p) -> int:
    """Score how much useful data a product has."""
    score = 0
    if p.image_url:
        score += 3
    if p.category and p.category != "Supermercato":
        score += 2
    if p.subcategory:
        score += 1
    if p.unit:
        score += 1
    if p.barcode:
        score += 1
    return score


if __name__ == "__main__":
    asyncio.run(main())
