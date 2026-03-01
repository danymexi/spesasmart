"""One-time script to backfill unit_reference on existing offers.

Infers unit_reference from raw_text, quantity, and the product's unit field:
  - Pattern "al kg", "/kg", "euro/kg" -> "kg"
  - Pattern "al lt", "al litro", "/l", "euro/l" -> "l"
  - Fallback: if price_per_unit is present and product.unit contains "kg"/"l" -> use that

Run from the backend directory:
    PYTHONPATH=. python scripts/backfill_unit_reference.py
"""

import asyncio
import logging
import re
import sys

from sqlalchemy import select, update

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Patterns to detect unit reference from text
KG_PATTERN = re.compile(
    r"(?:al\s+kg|/kg|euro/kg|eur/kg|\bprezzo\s+al\s+kg)",
    re.IGNORECASE,
)
L_PATTERN = re.compile(
    r"(?:al\s+l(?:t|itro)?|/l\b|euro/l|eur/l|\bprezzo\s+al\s+l(?:t|itro)?)",
    re.IGNORECASE,
)
PZ_PATTERN = re.compile(
    r"(?:al\s+pz|/pz|a\s+pezzo|cadauno|cad\.)",
    re.IGNORECASE,
)


def infer_unit_reference(
    raw_text: str | None,
    quantity: str | None,
    product_unit: str | None,
    has_price_per_unit: bool,
) -> str | None:
    """Infer unit_reference from available text fields."""
    # Check raw_text first (most reliable)
    for text in (raw_text, quantity):
        if not text:
            continue
        if KG_PATTERN.search(text):
            return "kg"
        if L_PATTERN.search(text):
            return "l"
        if PZ_PATTERN.search(text):
            return "pz"

    # Fallback: if price_per_unit exists, try to infer from product.unit
    if has_price_per_unit and product_unit:
        unit_lower = product_unit.lower().strip()
        if any(k in unit_lower for k in ("kg", "kilo", "gramm")):
            return "kg"
        if any(k in unit_lower for k in ("litro", "litri", " l", "ml")):
            return "l"
        if any(k in unit_lower for k in ("pz", "pezzo", "pezzi", "unit")):
            return "pz"

    return None


async def main():
    from app.database import async_session
    from app.models.offer import Offer
    from app.models.product import Product

    dry_run = "--dry-run" in sys.argv

    async with async_session() as session:
        # Load offers without unit_reference that have price_per_unit or raw_text
        result = await session.execute(
            select(
                Offer.id,
                Offer.raw_text,
                Offer.quantity,
                Offer.price_per_unit,
                Product.unit,
            )
            .join(Product, Offer.product_id == Product.id)
            .where(Offer.unit_reference.is_(None))
        )
        rows = result.all()
        logger.info("Found %d offers without unit_reference.", len(rows))

        updated = 0
        for offer_id, raw_text, quantity, price_per_unit, product_unit in rows:
            unit_ref = infer_unit_reference(
                raw_text=raw_text,
                quantity=quantity,
                product_unit=product_unit,
                has_price_per_unit=price_per_unit is not None,
            )
            if unit_ref:
                if not dry_run:
                    await session.execute(
                        update(Offer)
                        .where(Offer.id == offer_id)
                        .values(unit_reference=unit_ref)
                    )
                updated += 1

        if not dry_run:
            await session.commit()

        logger.info(
            "%s %d offers with unit_reference.",
            "Would update" if dry_run else "Updated",
            updated,
        )


if __name__ == "__main__":
    asyncio.run(main())
