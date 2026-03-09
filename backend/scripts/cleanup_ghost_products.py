"""Delete ghost/junk products from the catalog.

Targets:
1. Receipt ghosts: src=None, no offers (created by old create_or_match_product)
2. Esselunga loyalty rewards: "Gratis con ... Punti"
3. Junk entries: names like "200g", "500g", generic category pages

Run inside the backend container:
    env PYTHONPATH=/app python3 scripts/cleanup_ghost_products.py
"""

import asyncio
import logging
import re

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def main():
    from sqlalchemy import delete, select, update

    from app.database import async_session
    from app.models import Offer, Product, ShoppingListItem, ShoppingListItemProduct, UserWatchlist
    from app.models.purchase import PurchaseItem

    async with async_session() as db:
        # 1. Find all product IDs that have at least one offer
        has_offer_result = await db.execute(
            select(Offer.product_id).distinct()
        )
        has_offer_ids = {r[0] for r in has_offer_result.all()}
        logger.info("Products with offers: %d", len(has_offer_ids))

        # 2. Find all products WITHOUT offers
        all_products_result = await db.execute(select(Product))
        all_products = all_products_result.scalars().all()

        ghost_ids = set()
        for p in all_products:
            if p.id in has_offer_ids:
                continue

            is_ghost = False
            name = p.name or ""

            # Receipt ghosts: src=None, no offers
            if p.source is None:
                is_ghost = True

            # Esselunga loyalty rewards
            if "gratis con" in name.lower() and "punti" in name.lower():
                is_ghost = True

            # Junk entries: very short names that are just weights/quantities
            if re.match(r"^\d+[gml]+$", name.strip(), re.IGNORECASE):
                is_ghost = True

            # Penny category pages
            if p.source == "penny_online" and not any(c.isdigit() for c in name):
                # Generic category names from penny (no digits = no specific product)
                is_ghost = True

            # Non-product items that slipped through
            if re.search(r"(?i)shopper|sacchett|npsacchetto|buono\s+sconto|buona\s+spesa", name):
                is_ghost = True

            if is_ghost:
                ghost_ids.add(p.id)

        logger.info("Ghost products to delete: %d", len(ghost_ids))

        if not ghost_ids:
            logger.info("Nothing to clean up.")
            return

        # 3. Unlink from PurchaseItems
        unlinked = await db.execute(
            update(PurchaseItem)
            .where(PurchaseItem.product_id.in_(ghost_ids))
            .values(product_id=None)
        )
        logger.info("PurchaseItems unlinked: %d", unlinked.rowcount)

        # 4. Unlink from ShoppingListItems
        unlinked_sl = await db.execute(
            update(ShoppingListItem)
            .where(ShoppingListItem.product_id.in_(ghost_ids))
            .values(product_id=None)
        )
        logger.info("ShoppingListItems unlinked: %d", unlinked_sl.rowcount)

        # 5. Delete from ShoppingListItemProduct junction table
        deleted_junc = await db.execute(
            delete(ShoppingListItemProduct)
            .where(ShoppingListItemProduct.product_id.in_(ghost_ids))
        )
        logger.info("ShoppingListItemProduct links deleted: %d", deleted_junc.rowcount)

        # 6. Delete from user_watchlist
        deleted_wl = await db.execute(
            delete(UserWatchlist)
            .where(UserWatchlist.product_id.in_(ghost_ids))
        )
        logger.info("UserWatchlist entries deleted: %d", deleted_wl.rowcount)

        # 7. Delete the ghost products
        deleted = await db.execute(
            delete(Product).where(Product.id.in_(ghost_ids))
        )
        logger.info("Products deleted: %d", deleted.rowcount)

        await db.commit()

        logger.info("=" * 60)
        logger.info("Cleanup complete. Deleted %d ghost products.", deleted.rowcount)


if __name__ == "__main__":
    asyncio.run(main())
