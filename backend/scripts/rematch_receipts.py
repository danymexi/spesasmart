"""Re-match all existing PurchaseItems using the new find_receipt_match logic.

Run inside the backend container:
    python3 -m scripts.rematch_receipts
"""

import asyncio
import logging
import re
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Same blacklist as in purchases.py
_NON_PRODUCT_PATTERNS = re.compile(
    r"(?i)"
    r"sacchett[oi]|busta|shopper|"
    r"buono|coupon|sconto\s+tessera|"
    r"carta\s+fedelta|fidelity|punti|"
    r"cauzione|deposito\s+vuot|"
    r"subtotal|contante|bancomat|"
    r"carta\s+credito|carta\s+debito|"
    r"resto\s+euro|arrotondamento|"
    r"commissione|iva\b|"
    r"reso\b|rimborso|"
    r"cashback|acconto"
)


def _is_non_product_line(name: str) -> bool:
    return bool(_NON_PRODUCT_PATTERNS.search(name))


async def main():
    from sqlalchemy import select

    from app.database import async_session
    from app.models.purchase import PurchaseItem, PurchaseOrder
    from app.services.product_matcher import ProductMatcher

    matcher = ProductMatcher()

    async with async_session() as db:
        # Get all purchase items
        result = await db.execute(
            select(PurchaseItem).order_by(PurchaseItem.id)
        )
        items = result.scalars().all()
        logger.info("Total PurchaseItems: %d", len(items))

        cleared = 0
        matched = 0
        skipped_non_product = 0
        no_match = 0

        for item in items:
            name = (item.external_name or "").strip()
            if not name:
                continue

            # Clear old match
            old_pid = item.product_id
            item.product_id = None

            # Skip non-product lines
            if _is_non_product_line(name):
                if old_pid:
                    cleared += 1
                skipped_non_product += 1
                continue

            # Re-match with new logic
            try:
                product = await matcher.find_receipt_match(
                    name,
                    category=item.category,
                    session=db,
                )
                if product:
                    item.product_id = product.id
                    matched += 1
                    if old_pid and str(old_pid) != str(product.id):
                        logger.info(
                            "  CHANGED: '%s' -> %s (was %s)",
                            name, product.name, old_pid,
                        )
                else:
                    no_match += 1
                    if old_pid:
                        cleared += 1
                        logger.info("  LOST: '%s' (was pid=%s)", name, old_pid)
            except Exception as e:
                no_match += 1
                if old_pid:
                    cleared += 1
                logger.warning("  ERROR matching '%s': %s", name, e)

        await db.commit()

        logger.info("=" * 60)
        logger.info("RESULTS:")
        logger.info("  Total items:        %d", len(items))
        logger.info("  Matched:            %d", matched)
        logger.info("  No match:           %d", no_match)
        logger.info("  Skipped (non-prod): %d", skipped_non_product)
        logger.info("  Cleared old match:  %d", cleared)


if __name__ == "__main__":
    asyncio.run(main())
