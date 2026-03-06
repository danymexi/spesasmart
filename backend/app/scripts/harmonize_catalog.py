"""One-time catalog harmonisation script.

Processes the entire product catalog in 6 sequential phases:
  0. Garbage cleanup (delete products with garbage names and no offers)
  1. Brand normalisation (fix nulls, resolve aliases, split compounds)
  2. Re-categorisation (move products out of generic "Supermercato")
  3. Name standardisation (strip brand, normalise units, title-case)
  4. Deduplication (merge duplicates, migrate all FKs)
  5. Validation report

Run from the backend directory:
    docker compose exec backend python -m app.scripts.harmonize_catalog
    docker compose exec backend python -m app.scripts.harmonize_catalog --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from collections import defaultdict

from sqlalchemy import delete, func, select, update

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

BATCH_SIZE = 500


# -----------------------------------------------------------------------
# Phase 0 — Garbage cleanup
# -----------------------------------------------------------------------

_GARBAGE_NAMES = {"-", ".", "--", "...", "N/A", "n/a", ""}


async def phase0_garbage_cleanup(session, dry_run: bool) -> dict:
    """Delete products with garbage names that have no active offers."""
    from app.models import Product
    from app.models.offer import Offer
    from app.models.purchase import PurchaseItem
    from app.models.user import ShoppingListItem, ShoppingListItemProduct, UserWatchlist

    # Find garbage products: name too short or in garbage set
    result = await session.execute(select(Product))
    all_products = list(result.scalars().all())

    garbage_ids = []
    for p in all_products:
        name = (p.name or "").strip()
        if len(name) < 2 or name in _GARBAGE_NAMES:
            garbage_ids.append(p.id)

    stats = {"garbage_found": len(garbage_ids), "deleted": 0, "skipped_has_offers": 0}

    if not garbage_ids:
        logger.info("Phase 0 — No garbage products found.")
        return stats

    # Check which garbage products have offers
    offers_result = await session.execute(
        select(Offer.product_id)
        .where(Offer.product_id.in_(garbage_ids))
        .distinct()
    )
    has_offers = {row[0] for row in offers_result.fetchall()}

    to_delete = [pid for pid in garbage_ids if pid not in has_offers]
    stats["skipped_has_offers"] = len(has_offers)

    if to_delete and not dry_run:
        # Clean up all FKs first
        await session.execute(
            delete(ShoppingListItemProduct).where(
                ShoppingListItemProduct.product_id.in_(to_delete)
            )
        )
        await session.execute(
            delete(UserWatchlist).where(UserWatchlist.product_id.in_(to_delete))
        )
        await session.execute(
            update(ShoppingListItem)
            .where(ShoppingListItem.product_id.in_(to_delete))
            .values(product_id=None)
        )
        await session.execute(
            update(PurchaseItem)
            .where(PurchaseItem.product_id.in_(to_delete))
            .values(product_id=None)
        )
        await session.execute(
            delete(Product).where(Product.id.in_(to_delete))
        )
        stats["deleted"] = len(to_delete)
        await session.flush()

    logger.info(
        "Phase 0 — Garbage: %d found, %d deleted, %d skipped (have offers).",
        stats["garbage_found"], stats["deleted"] if not dry_run else len(to_delete),
        stats["skipped_has_offers"],
    )
    return stats


# -----------------------------------------------------------------------
# Phase 1 — Brand normalisation
# -----------------------------------------------------------------------

async def phase1_normalize_brands(session, dry_run: bool) -> dict:
    """Fix missing/invalid brands and normalise all brand values."""
    from app.models import Product
    from app.services.product_matcher import (
        BRAND_ALIASES,
        PRIVATE_LABELS,
        ProductMatcher,
    )

    result = await session.execute(select(Product))
    all_products = list(result.scalars().all())

    stats = {
        "total": len(all_products),
        "brand_was_null": 0,
        "brand_extracted": 0,
        "brand_normalised": 0,
        "compound_split": 0,
    }

    for product in all_products:
        original_brand = product.brand

        # Fix "Null"/"null"/empty → None
        if product.brand and product.brand.strip().lower() in ("null", "none", ""):
            product.brand = None

        # Try to extract brand from product name if brand is missing
        if not product.brand:
            stats["brand_was_null"] += 1
            extracted = ProductMatcher.extract_brand_from_product_name(product.name)
            if extracted:
                product.brand = extracted
                stats["brand_extracted"] += 1
                if not dry_run:
                    logger.debug(
                        "  Extracted brand '%s' from name '%s'",
                        extracted, product.name[:60],
                    )

        # Normalise brand (aliases, compound split, title-case)
        if product.brand:
            normalised = ProductMatcher.normalize_brand(product.brand)
            if normalised != original_brand:
                old = original_brand or "(null)"
                product.brand = normalised
                stats["brand_normalised"] += 1

    if not dry_run:
        await session.flush()

    logger.info(
        "Phase 1 — Brands: %d total, %d were null, %d extracted from name, "
        "%d normalised.",
        stats["total"], stats["brand_was_null"],
        stats["brand_extracted"], stats["brand_normalised"],
    )
    return stats


# -----------------------------------------------------------------------
# Phase 2 — Re-categorisation
# -----------------------------------------------------------------------

async def phase2_recategorize(session, dry_run: bool) -> dict:
    """Move products out of the generic 'Supermercato' category."""
    from app.models import Product
    from app.services.product_matcher import ProductMatcher

    result = await session.execute(
        select(Product).where(
            (Product.category == "Supermercato")
            | (Product.category.is_(None))
        )
    )
    products = list(result.scalars().all())

    stats = {
        "to_recategorize": len(products),
        "recategorized": 0,
        "by_keyword": 0,
        "by_brand": 0,
        "still_generic": 0,
    }

    for product in products:
        new_cat = ProductMatcher.categorize_by_keywords(
            product.name, product.brand
        )
        if new_cat:
            product.category = new_cat
            stats["recategorized"] += 1
            # Determine source of categorisation for stats
            text = product.name.lower()
            from app.services.product_matcher import CATEGORY_KEYWORDS
            found_keyword = False
            for cat, keywords in CATEGORY_KEYWORDS.items():
                if cat == new_cat:
                    for kw in keywords:
                        if kw in text:
                            found_keyword = True
                            break
                if found_keyword:
                    break
            if found_keyword:
                stats["by_keyword"] += 1
            else:
                stats["by_brand"] += 1
        else:
            stats["still_generic"] += 1

    if not dry_run:
        await session.flush()

    logger.info(
        "Phase 2 — Categories: %d to recategorize, %d done "
        "(%d by keyword, %d by brand), %d still generic.",
        stats["to_recategorize"], stats["recategorized"],
        stats["by_keyword"], stats["by_brand"], stats["still_generic"],
    )
    return stats


# -----------------------------------------------------------------------
# Phase 3 — Name standardisation
# -----------------------------------------------------------------------

async def phase3_clean_names(session, dry_run: bool) -> dict:
    """Standardise all product names: strip brand, normalise units, title-case."""
    from app.models import Product
    from app.services.product_matcher import ProductMatcher

    result = await session.execute(select(Product))
    all_products = list(result.scalars().all())

    stats = {"total": len(all_products), "cleaned": 0, "unchanged": 0}

    for product in all_products:
        cleaned = ProductMatcher.clean_product_name(product.name, product.brand)
        if cleaned and cleaned != product.name:
            product.name = cleaned
            stats["cleaned"] += 1
        else:
            stats["unchanged"] += 1

    if not dry_run:
        await session.flush()

    logger.info(
        "Phase 3 — Names: %d total, %d cleaned, %d unchanged.",
        stats["total"], stats["cleaned"], stats["unchanged"],
    )
    return stats


# -----------------------------------------------------------------------
# Phase 4 — Deduplication
# -----------------------------------------------------------------------

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


async def phase4_deduplicate(session, dry_run: bool) -> dict:
    """Find and merge duplicate products, migrating all foreign keys.

    Includes cross-brand comparison for private-label products and
    category guards to prevent false merges.
    """
    from app.models import Product
    from app.models.offer import Offer
    from app.models.purchase import PurchaseItem
    from app.models.user import ShoppingListItem, ShoppingListItemProduct, UserWatchlist
    from app.services.product_matcher import PRIVATE_LABELS, ProductMatcher

    pm = ProductMatcher()

    result = await session.execute(select(Product))
    all_products = list(result.scalars().all())

    # Group by canonical brand
    by_brand: dict[str | None, list] = defaultdict(list)
    for p in all_products:
        by_brand[p.brand].append(p)

    merge_pairs: list[tuple] = []  # (keep, delete)
    seen_ids = set()

    def _categories_conflict(p1, p2) -> bool:
        """Return True if both have a real category and they differ."""
        c1 = (p1.category or "").strip()
        c2 = (p2.category or "").strip()
        return (
            bool(c1) and bool(c2)
            and c1 != c2
            and c1 != "Supermercato"
            and c2 != "Supermercato"
        )

    # --- Within-brand comparison ---
    for brand, products in by_brand.items():
        if len(products) < 2:
            continue

        products.sort(key=lambda p: _richness(p), reverse=True)

        for i, p1 in enumerate(products):
            if p1.id in seen_ids:
                continue
            for j in range(i + 1, len(products)):
                p2 = products[j]
                if p2.id in seen_ids:
                    continue

                if p1.source and p2.source and p1.source == p2.source:
                    continue

                if _categories_conflict(p1, p2):
                    continue

                score = pm.fuzzy_match(
                    p1.name, p2.name,
                    brand1=p1.brand, brand2=p2.brand,
                )

                cb1 = pm.normalize_brand(p1.brand)
                cb2 = pm.normalize_brand(p2.brand)
                threshold = 80 if cb1 and cb2 and cb1 == cb2 else 85

                if score >= threshold:
                    merge_pairs.append((p1, p2))
                    seen_ids.add(p2.id)

    # --- Cross-brand: private-label vs generic/branded ---
    # e.g. "Esselunga Naturama Finocchi" vs unbranded "Finocchi"
    private_label_products = []
    non_private_products = []
    for p in all_products:
        if p.id in seen_ids:
            continue
        if p.brand and p.brand in PRIVATE_LABELS:
            private_label_products.append(p)
        elif not p.brand:
            non_private_products.append(p)

    for pl_prod in private_label_products:
        if pl_prod.id in seen_ids:
            continue
        # Strip the private-label prefix to get the generic name
        stripped = pm._strip_private_label(pl_prod.name)
        if stripped == pl_prod.name:
            continue  # No prefix was stripped

        for gen_prod in non_private_products:
            if gen_prod.id in seen_ids:
                continue

            if _categories_conflict(pl_prod, gen_prod):
                continue

            score = pm.fuzzy_match(
                stripped, gen_prod.name,
                brand1=None, brand2=None,
            )
            if score >= 88:  # Higher threshold for cross-brand
                # Keep the one with more data
                if _richness(pl_prod) >= _richness(gen_prod):
                    merge_pairs.append((pl_prod, gen_prod))
                    seen_ids.add(gen_prod.id)
                else:
                    merge_pairs.append((gen_prod, pl_prod))
                    seen_ids.add(pl_prod.id)

    stats = {
        "candidates": len(all_products),
        "duplicate_pairs": len(merge_pairs),
        "merged": 0,
        "offers_migrated": 0,
        "watchlist_migrated": 0,
        "shopping_migrated": 0,
        "shopping_linked_migrated": 0,
        "purchase_items_migrated": 0,
    }

    logger.info(
        "Phase 4 — Dedup: found %d duplicate pairs to merge.", len(merge_pairs)
    )

    # Log sample merges
    for keep, dup in merge_pairs[:20]:
        logger.info(
            "  MERGE: [%s] '%s' (%s) <- [%s] '%s' (%s)",
            keep.source, keep.name[:40], keep.brand,
            dup.source, dup.name[:40], dup.brand,
        )
    if len(merge_pairs) > 20:
        logger.info("  ... and %d more.", len(merge_pairs) - 20)

    # Export merge pairs for review (dry-run or live)
    if merge_pairs:
        pairs_export = [
            {
                "keep": {"id": str(k.id), "name": k.name, "brand": k.brand, "category": k.category, "source": k.source},
                "delete": {"id": str(d.id), "name": d.name, "brand": d.brand, "category": d.category, "source": d.source},
            }
            for k, d in merge_pairs
        ]
        export_path = "/tmp/dedup_pairs.json"
        with open(export_path, "w") as f:
            json.dump(pairs_export, f, indent=2, ensure_ascii=False)
        logger.info("Merge pairs exported to %s", export_path)

    if dry_run or not merge_pairs:
        return stats

    # Execute merges
    for keep, dup in merge_pairs:
        try:
            # 1. Migrate offers
            offer_result = await session.execute(
                update(Offer)
                .where(Offer.product_id == dup.id)
                .values(product_id=keep.id)
            )
            stats["offers_migrated"] += offer_result.rowcount

            # 2. Migrate watchlist (handle unique constraint)
            existing_wl = await session.execute(
                select(UserWatchlist.user_id)
                .where(UserWatchlist.product_id == keep.id)
            )
            existing_user_ids = {row[0] for row in existing_wl.fetchall()}

            if existing_user_ids:
                await session.execute(
                    delete(UserWatchlist).where(
                        UserWatchlist.product_id == dup.id,
                        UserWatchlist.user_id.in_(existing_user_ids),
                    )
                )

            wl_result = await session.execute(
                update(UserWatchlist)
                .where(UserWatchlist.product_id == dup.id)
                .values(product_id=keep.id)
            )
            stats["watchlist_migrated"] += wl_result.rowcount

            # 3. Migrate shopping list items
            sl_result = await session.execute(
                update(ShoppingListItem)
                .where(ShoppingListItem.product_id == dup.id)
                .values(product_id=keep.id)
            )
            stats["shopping_migrated"] += sl_result.rowcount

            # 4. Migrate ShoppingListItemProduct (handle unique constraint)
            existing_slp = await session.execute(
                select(ShoppingListItemProduct.item_id)
                .where(ShoppingListItemProduct.product_id == keep.id)
            )
            existing_item_ids = {row[0] for row in existing_slp.fetchall()}

            if existing_item_ids:
                await session.execute(
                    delete(ShoppingListItemProduct).where(
                        ShoppingListItemProduct.product_id == dup.id,
                        ShoppingListItemProduct.item_id.in_(existing_item_ids),
                    )
                )

            slp_result = await session.execute(
                update(ShoppingListItemProduct)
                .where(ShoppingListItemProduct.product_id == dup.id)
                .values(product_id=keep.id)
            )
            stats["shopping_linked_migrated"] += slp_result.rowcount

            # 5. Migrate PurchaseItem
            pi_result = await session.execute(
                update(PurchaseItem)
                .where(PurchaseItem.product_id == dup.id)
                .values(product_id=keep.id)
            )
            stats["purchase_items_migrated"] += pi_result.rowcount

            # 6. Enrich the kept product with missing data from duplicate
            if not keep.image_url and dup.image_url:
                keep.image_url = dup.image_url
            if (not keep.category or keep.category == "Supermercato") and dup.category:
                keep.category = dup.category
            if not keep.subcategory and dup.subcategory:
                keep.subcategory = dup.subcategory
            if not keep.unit and dup.unit:
                keep.unit = dup.unit
            if not keep.barcode and dup.barcode:
                keep.barcode = dup.barcode

            # 7. Delete the duplicate
            await session.execute(
                delete(Product).where(Product.id == dup.id)
            )

            stats["merged"] += 1

        except Exception:
            logger.exception("Failed to merge %s -> %s", dup.id, keep.id)
            await session.rollback()
            return stats

    await session.flush()

    logger.info(
        "Phase 4 — Merged %d duplicates. Offers: %d, watchlist: %d, "
        "shopping: %d, linked: %d, purchases: %d.",
        stats["merged"], stats["offers_migrated"],
        stats["watchlist_migrated"], stats["shopping_migrated"],
        stats["shopping_linked_migrated"], stats["purchase_items_migrated"],
    )
    return stats


# -----------------------------------------------------------------------
# Phase 5 — Validation & report
# -----------------------------------------------------------------------

async def phase5_report(session, pre_stats: dict) -> dict:
    """Generate a before/after validation report."""
    from app.models import Product
    from app.models.offer import Offer
    from app.models.purchase import PurchaseItem
    from app.models.user import ShoppingListItem, ShoppingListItemProduct, UserWatchlist

    # Total products
    total = (await session.execute(
        select(func.count()).select_from(Product)
    )).scalar()

    # Products per category
    cat_counts = (await session.execute(
        select(Product.category, func.count())
        .group_by(Product.category)
        .order_by(func.count().desc())
    )).fetchall()

    # Products without brand
    no_brand = (await session.execute(
        select(func.count()).select_from(Product)
        .where(Product.brand.is_(None))
    )).scalar()

    # Products in "Supermercato"
    superm = (await session.execute(
        select(func.count()).select_from(Product)
        .where(Product.category == "Supermercato")
    )).scalar()

    # Orphan checks: offers pointing to non-existent products
    orphan_offers = (await session.execute(
        select(func.count()).select_from(Offer)
        .where(~Offer.product_id.in_(select(Product.id)))
    )).scalar()

    orphan_wl = (await session.execute(
        select(func.count()).select_from(UserWatchlist)
        .where(~UserWatchlist.product_id.in_(select(Product.id)))
    )).scalar()

    orphan_sl = (await session.execute(
        select(func.count()).select_from(ShoppingListItem)
        .where(
            ShoppingListItem.product_id.isnot(None),
            ~ShoppingListItem.product_id.in_(select(Product.id)),
        )
    )).scalar()

    orphan_slp = (await session.execute(
        select(func.count()).select_from(ShoppingListItemProduct)
        .where(~ShoppingListItemProduct.product_id.in_(select(Product.id)))
    )).scalar()

    orphan_pi = (await session.execute(
        select(func.count()).select_from(PurchaseItem)
        .where(
            PurchaseItem.product_id.isnot(None),
            ~PurchaseItem.product_id.in_(select(Product.id)),
        )
    )).scalar()

    # Products by source
    source_counts = (await session.execute(
        select(Product.source, func.count())
        .group_by(Product.source)
        .order_by(func.count().desc())
    )).fetchall()

    logger.info("=" * 60)
    logger.info("HARMONISATION REPORT")
    logger.info("=" * 60)
    logger.info("Products: %d (before: %d)", total, pre_stats.get("total", "?"))
    logger.info("Without brand: %d", no_brand)
    logger.info("In 'Supermercato': %d (%.1f%%)", superm, superm / total * 100 if total else 0)
    logger.info("")
    logger.info("By category:")
    for cat, count in cat_counts[:25]:
        pct = count / total * 100 if total else 0
        logger.info("  %-30s %5d  (%.1f%%)", cat or "(null)", count, pct)
    logger.info("")
    logger.info("By source:")
    for src, count in source_counts:
        logger.info("  %-25s %5d", src or "(null)", count)
    logger.info("")
    logger.info("Orphan checks:")
    logger.info("  Offers → missing product:           %d", orphan_offers)
    logger.info("  Watchlist → missing product:         %d", orphan_wl)
    logger.info("  Shopping list → missing product:     %d", orphan_sl)
    logger.info("  Shopping linked → missing product:   %d", orphan_slp)
    logger.info("  Purchase items → missing product:    %d", orphan_pi)
    logger.info("=" * 60)

    return {
        "total_products": total,
        "no_brand": no_brand,
        "supermercato_count": superm,
        "orphan_offers": orphan_offers,
        "orphan_watchlist": orphan_wl,
        "orphan_shopping": orphan_sl,
        "orphan_shopping_linked": orphan_slp,
        "orphan_purchase_items": orphan_pi,
    }


# -----------------------------------------------------------------------
# Main orchestrator
# -----------------------------------------------------------------------

async def harmonize(dry_run: bool = False):
    from app.database import async_session
    from app.models import Product

    mode = "DRY RUN" if dry_run else "LIVE"
    logger.info("Starting catalog harmonisation [%s]...", mode)

    async with async_session() as session:
        # Pre-stats for the report
        pre_total = (await session.execute(
            select(func.count()).select_from(Product)
        )).scalar()
        pre_stats = {"total": pre_total}

        # Phase 0
        logger.info("-" * 40)
        logger.info("PHASE 0: Garbage cleanup")
        logger.info("-" * 40)
        await phase0_garbage_cleanup(session, dry_run)

        # Phase 1
        logger.info("-" * 40)
        logger.info("PHASE 1: Brand normalisation")
        logger.info("-" * 40)
        await phase1_normalize_brands(session, dry_run)

        # Phase 2
        logger.info("-" * 40)
        logger.info("PHASE 2: Re-categorisation")
        logger.info("-" * 40)
        await phase2_recategorize(session, dry_run)

        # Phase 3
        logger.info("-" * 40)
        logger.info("PHASE 3: Name standardisation")
        logger.info("-" * 40)
        await phase3_clean_names(session, dry_run)

        # Phase 4
        logger.info("-" * 40)
        logger.info("PHASE 4: Deduplication")
        logger.info("-" * 40)
        await phase4_deduplicate(session, dry_run)

        # Commit all changes (or rollback if dry run)
        if dry_run:
            logger.info("DRY RUN — rolling back all changes.")
            await session.rollback()
        else:
            logger.info("Committing all changes...")
            await session.commit()

        # Phase 5 (report — always runs, reads committed/rolled-back state)
        logger.info("-" * 40)
        logger.info("PHASE 5: Validation report")
        logger.info("-" * 40)

    # Open a fresh session for the report (reads committed state)
    if not dry_run:
        async with async_session() as session:
            await phase5_report(session, pre_stats)
    else:
        logger.info("(Report skipped in dry-run mode — data was rolled back.)")

    logger.info("Harmonisation complete.")


def main():
    parser = argparse.ArgumentParser(
        description="Harmonise the SpesaSmart product catalog."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying the database.",
    )
    args = parser.parse_args()
    asyncio.run(harmonize(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
