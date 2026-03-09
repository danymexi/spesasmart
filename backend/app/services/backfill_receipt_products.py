"""Backfill product_id on PurchaseItems from receipt uploads.

Step 1: fuzzy matching via ProductMatcher (with receipt brand expansion).
Step 2: AI matching via Claude/Gemini for items that fuzzy match failed on.
Step 3: Create new products for anything still unmatched.

Also provides rematch_ghost_products() to clean up ghost products created
by previous backfills that didn't expand receipt abbreviations.
"""

import json
import logging
import re
import uuid

from sqlalchemy import func, or_, select, update

from app.config import get_settings
from app.database import async_session
from app.models import Product
from app.models.purchase import PurchaseItem, PurchaseOrder
from app.services.product_matcher import (
    BRAND_ALIASES,
    ProductMatcher,
    expand_receipt_brands,
)

logger = logging.getLogger(__name__)

AI_MATCH_SYSTEM_PROMPT = """\
You are a product-matching assistant for an Italian supermarket app.

You will receive a list of product names from a receipt (OCR, often truncated or \
abbreviated) and a list of candidate products from the catalog database.

For each receipt item, decide which catalog product (if any) is the SAME product. \
Consider abbreviations, truncations, and OCR errors. Only match if you are confident \
they are the same product (same brand, same type, same size when visible).

Return ONLY a JSON array. Each element: {"item": "<receipt name>", "match_id": "<uuid>" | null}
Return null for match_id when no candidate is a confident match.
No markdown fences, no commentary — just the JSON array."""

# Max items per AI call to save tokens
_AI_BATCH_SIZE = 10
_AI_TIMEOUT = 30

# Non-product line filter (bags, discounts, payment methods, etc.)
_NON_PRODUCT_RE = re.compile(
    r"(?i)"
    r"sacchett[oi]|busta|shopper|"
    r"buono|coupon|sconto|"
    r"carta\s+fedelta|fidelity|punti|"
    r"cauzione|deposito|"
    r"subtotal|contante|bancomat|"
    r"carta\s+credito|carta\s+debito|"
    r"resto\s+euro|arrotondamento|"
    r"commissione|iva\b|"
    r"reso\b|rimborso|cashback|acconto"
)


async def _get_candidates_for_item(
    item: PurchaseItem,
    session,
) -> list[dict]:
    """Query DB for candidate products using ILIKE on significant tokens.

    Expands receipt brand abbreviations before tokenizing, and adds brand
    filter when a brand is detected from abbreviation expansion.
    """
    # Expand receipt brand abbreviations
    expanded_name, detected_brand = expand_receipt_brands(item.external_name)

    tokens = [t for t in expanded_name.split() if len(t) > 3]
    if not tokens:
        tokens = [t for t in expanded_name.split() if len(t) > 2]
    if not tokens:
        return []

    # Use up to 3 tokens for ILIKE OR filter
    significant = tokens[:3]
    filters = [Product.name.ilike(f"%{tok}%") for tok in significant]

    # Also search by detected brand
    if detected_brand:
        filters.append(Product.brand.ilike(f"%{detected_brand}%"))

    stmt = select(Product).where(or_(*filters))
    if item.category:
        stmt = stmt.where(Product.category.ilike(f"%{item.category}%"))
    stmt = stmt.limit(30)

    result = await session.execute(stmt)
    candidates = result.scalars().all()
    return [
        {"id": str(c.id), "name": c.name, "brand": c.brand or ""}
        for c in candidates
    ]


def _build_ai_prompt(
    batch: list[tuple[PurchaseItem, list[dict]]],
) -> str:
    """Build the user message for the AI matching call."""
    lines = ["RECEIPT ITEMS:"]
    for i, (item, _) in enumerate(batch, 1):
        lines.append(f"  {i}. \"{item.external_name}\" (category: {item.category or 'unknown'})")

    lines.append("\nCATALOG CANDIDATES:")
    seen_ids: set[str] = set()
    for item, candidates in batch:
        for c in candidates:
            if c["id"] not in seen_ids:
                seen_ids.add(c["id"])
                lines.append(f'  - id={c["id"]} name="{c["name"]}" brand="{c["brand"]}"')

    lines.append(
        "\nFor each receipt item, return the matching catalog product id or null."
    )
    return "\n".join(lines)


def _parse_ai_response(raw: str) -> list[dict]:
    """Parse AI JSON response, handling markdown fences."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    try:
        data = json.loads(text.strip())
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        logger.warning("AI matching: could not parse response: %s", raw[:500])
    return []


async def _ai_match_claude(prompt: str) -> list[dict]:
    """Call Claude for AI matching."""
    import anthropic

    settings = get_settings()
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        temperature=0.0,
        system=AI_MATCH_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
        timeout=_AI_TIMEOUT,
    )
    return _parse_ai_response(response.content[0].text)


async def _ai_match_gemini(prompt: str) -> list[dict]:
    """Call Gemini as fallback for AI matching."""
    import google.generativeai as genai

    settings = get_settings()
    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(
        model_name=settings.gemini_model,
        system_instruction=AI_MATCH_SYSTEM_PROMPT,
        generation_config=genai.GenerationConfig(
            temperature=0.0,
            max_output_tokens=4096,
            response_mime_type="application/json",
        ),
    )
    response = await model.generate_content_async(prompt)
    return _parse_ai_response(response.text)


async def _ai_match_batch(
    batch: list[tuple[PurchaseItem, list[dict]]],
) -> dict[str, str | None]:
    """Send a batch to AI and return {external_name: product_id | None}.

    Tries Claude first, falls back to Gemini, returns empty on total failure.
    """
    prompt = _build_ai_prompt(batch)
    settings = get_settings()

    results: list[dict] = []
    try:
        if settings.anthropic_api_key:
            results = await _ai_match_claude(prompt)
        elif settings.gemini_api_key:
            results = await _ai_match_gemini(prompt)
        else:
            logger.debug("AI matching: no API key configured, skipping")
            return {}
    except Exception:
        # If Claude fails, try Gemini as fallback
        if settings.anthropic_api_key and settings.gemini_api_key:
            try:
                logger.warning("AI matching: Claude failed, trying Gemini fallback")
                results = await _ai_match_gemini(prompt)
            except Exception:
                logger.warning("AI matching: Gemini fallback also failed")
                return {}
        else:
            logger.warning("AI matching: AI call failed, skipping batch")
            return {}

    # Build lookup: normalize item names for matching
    name_to_match: dict[str, str | None] = {}
    for entry in results:
        item_name = entry.get("item", "")
        match_id = entry.get("match_id")
        if item_name and match_id:
            name_to_match[item_name] = match_id

    return name_to_match


async def backfill_unmatched_receipt_items(user_id: uuid.UUID) -> dict:
    """Find PurchaseItems with product_id=NULL from receipt uploads and try to match them.

    Step 1: Fuzzy matching via ProductMatcher (with receipt brand expansion).
    Step 2: AI matching via Claude/Gemini for remaining unmatched items.
    Step 3: Create new products for anything still unmatched.

    Non-product lines (SHOPPER, SCONTO, etc.) are skipped entirely.

    Returns a summary dict with counts of matched and total items processed.
    """
    matcher = ProductMatcher()
    matched = 0
    skipped_non_product = 0
    total = 0

    async with async_session() as session:
        stmt = (
            select(PurchaseItem)
            .join(PurchaseOrder, PurchaseItem.order_id == PurchaseOrder.id)
            .where(
                PurchaseOrder.user_id == user_id,
                PurchaseOrder.raw_data["source"].as_string() == "receipt_upload",
                PurchaseItem.product_id.is_(None),
            )
        )
        result = await session.execute(stmt)
        items = result.scalars().all()
        total = len(items)

        # ── Step 0: Filter non-product items ──
        product_items: list[PurchaseItem] = []
        for item in items:
            if _NON_PRODUCT_RE.search(item.external_name):
                skipped_non_product += 1
                logger.debug("Skipping non-product: '%s'", item.external_name)
                continue
            product_items.append(item)

        if skipped_non_product:
            logger.info("Skipped %d non-product items", skipped_non_product)

        # ── Step 1: Fuzzy matching with receipt brand expansion ──
        still_unmatched: list[PurchaseItem] = []
        for item in product_items:
            try:
                # Expand receipt abbreviations before matching
                expanded_name, detected_brand = expand_receipt_brands(
                    item.external_name
                )
                brand = detected_brand or item.brand

                product = await matcher.find_matching_product(
                    expanded_name,
                    brand,
                    session=session,
                )
                if product is not None:
                    item.product_id = product.id
                    matched += 1
                else:
                    still_unmatched.append(item)
            except Exception:
                logger.debug("Backfill fuzzy matching failed for '%s'", item.external_name)
                still_unmatched.append(item)

        # ── Step 2: AI matching for items that fuzzy matching couldn't match ──
        unique_unmatched = still_unmatched

        if unique_unmatched:
            logger.info(
                "AI matching: %d items unmatched after fuzzy, attempting AI",
                len(unique_unmatched),
            )

            # Gather candidates for each unmatched item
            items_with_candidates: list[tuple[PurchaseItem, list[dict]]] = []
            for item in unique_unmatched:
                candidates = await _get_candidates_for_item(item, session)
                if candidates:
                    items_with_candidates.append((item, candidates))

            # Process in batches
            ai_matched = 0
            for i in range(0, len(items_with_candidates), _AI_BATCH_SIZE):
                batch = items_with_candidates[i : i + _AI_BATCH_SIZE]
                name_to_match = await _ai_match_batch(batch)

                for item, _ in batch:
                    product_id_str = name_to_match.get(item.external_name)
                    if product_id_str:
                        try:
                            pid = uuid.UUID(product_id_str)
                            # Verify the product exists
                            check = await session.execute(
                                select(Product.id).where(Product.id == pid)
                            )
                            if check.scalar_one_or_none() is not None:
                                item.product_id = pid
                                ai_matched += 1
                                logger.info(
                                    "AI matched '%s' -> product %s",
                                    item.external_name,
                                    pid,
                                )
                        except (ValueError, Exception):
                            logger.debug(
                                "AI match invalid product_id for '%s': %s",
                                item.external_name,
                                product_id_str,
                            )

            if ai_matched > 0:
                matched += ai_matched
                logger.info("AI matching: %d additional items matched", ai_matched)

        # ── Step 3: Create new products for anything still unmatched ──
        final_unmatched = [it for it in product_items if it.product_id is None]
        for item in final_unmatched:
            try:
                # Use expanded name for cleaner product creation
                expanded_name, detected_brand = expand_receipt_brands(
                    item.external_name
                )
                product = await matcher.create_or_match_product(
                    {
                        "name": expanded_name,
                        "brand": detected_brand or item.brand,
                        "category": item.category,
                    },
                    session=session,
                )
                item.product_id = product.id
                matched += 1
            except Exception:
                logger.debug("Backfill create failed for '%s'", item.external_name)

        if matched > 0:
            await session.commit()

    logger.info(
        "Backfill for user %s: %d/%d items matched (%d non-product skipped)",
        user_id, matched, total, skipped_non_product,
    )
    return {
        "matched": matched,
        "total": total,
        "skipped_non_product": skipped_non_product,
    }


async def rematch_ghost_products(user_id: uuid.UUID) -> dict:
    """Find and clean up ghost products created by previous backfills.

    Ghost products are identified as:
    - name == UPPER(name) (all-caps, from receipt OCR)
    - brand is NULL or empty
    - short name (< 40 chars, typical receipt line length)

    For each ghost:
    1. If it's a non-product (SHOPPER, SCONTO, etc.) → unlink items, delete ghost
    2. Otherwise → expand abbreviations, re-run fuzzy + AI matching
    3. If a real match is found → reassign items to real product, delete ghost
    4. Delete orphan ghosts (no items linked)

    Returns summary dict.
    """
    matcher = ProductMatcher()
    rematched = 0
    deleted_non_product = 0
    deleted_orphan = 0
    total_ghosts = 0

    async with async_session() as session:
        # Find ghost products: all-caps name, no brand, short
        stmt = select(Product).where(
            Product.name == func.upper(Product.name),
            func.length(Product.name) < 40,
            or_(Product.brand.is_(None), Product.brand == ""),
        )
        result = await session.execute(stmt)
        ghosts: list[Product] = list(result.scalars().all())
        total_ghosts = len(ghosts)
        logger.info("Found %d ghost products to process", total_ghosts)

        for ghost in ghosts:
            # Count linked purchase_items
            item_count_result = await session.execute(
                select(func.count(PurchaseItem.id)).where(
                    PurchaseItem.product_id == ghost.id
                )
            )
            item_count = item_count_result.scalar() or 0

            # 1. Delete orphans (no items linked)
            if item_count == 0:
                await session.delete(ghost)
                deleted_orphan += 1
                logger.debug("Deleted orphan ghost: '%s'", ghost.name)
                continue

            # 2. Non-product check
            if _NON_PRODUCT_RE.search(ghost.name):
                # Unlink all items
                await session.execute(
                    update(PurchaseItem)
                    .where(PurchaseItem.product_id == ghost.id)
                    .values(product_id=None)
                )
                await session.delete(ghost)
                deleted_non_product += 1
                logger.info(
                    "Deleted non-product ghost '%s' (%d items unlinked)",
                    ghost.name, item_count,
                )
                continue

            # 3. Try to rematch: expand abbreviations, fuzzy match
            expanded_name, detected_brand = expand_receipt_brands(ghost.name)

            real_product = await matcher.find_matching_product(
                expanded_name,
                detected_brand,
                session=session,
            )

            # 4. If no fuzzy match, try find_receipt_match (lower threshold)
            if real_product is None:
                real_product = await matcher.find_receipt_match(
                    expanded_name,
                    session=session,
                )

            if real_product is not None and real_product.id != ghost.id:
                # Reassign all items to the real product
                await session.execute(
                    update(PurchaseItem)
                    .where(PurchaseItem.product_id == ghost.id)
                    .values(product_id=real_product.id)
                )
                await session.delete(ghost)
                rematched += 1
                logger.info(
                    "Rematched ghost '%s' -> '%s' [%s] (%d items)",
                    ghost.name, real_product.name, real_product.brand or "no brand",
                    item_count,
                )
            else:
                logger.debug(
                    "Could not rematch ghost '%s' (expanded: '%s')",
                    ghost.name, expanded_name,
                )

        await session.commit()

    logger.info(
        "Ghost cleanup for user %s: %d rematched, %d non-product deleted, "
        "%d orphans deleted (of %d total ghosts)",
        user_id, rematched, deleted_non_product, deleted_orphan, total_ghosts,
    )
    return {
        "total_ghosts": total_ghosts,
        "rematched": rematched,
        "deleted_non_product": deleted_non_product,
        "deleted_orphan": deleted_orphan,
        "remaining": total_ghosts - rematched - deleted_non_product - deleted_orphan,
    }


async def cleanup_ghost_names() -> dict:
    """Rename remaining ghost products: expand abbreviations, title-case, set brand.

    Targets products where name == UPPER(name) and (brand IS NULL or empty).
    Does NOT delete or rematch — just cleans up the display name and brand.

    Returns summary dict.
    """
    renamed = 0
    total = 0

    async with async_session() as session:
        stmt = select(Product).where(
            Product.name == func.upper(Product.name),
            func.length(Product.name) < 40,
            or_(Product.brand.is_(None), Product.brand == ""),
        )
        result = await session.execute(stmt)
        ghosts: list[Product] = list(result.scalars().all())
        total = len(ghosts)

        for ghost in ghosts:
            original = ghost.name

            # 1. Expand receipt brand abbreviations
            expanded, detected_brand = expand_receipt_brands(original)

            # 2. Expand multi-token and single-token abbreviations
            #    via ProductMatcher's normalize pipeline (but we want display form)
            #    So we do a lighter cleanup: expand "/" separators, remove weight suffixes
            expanded = re.sub(r"(\w)/(\w)", r"\1 / \2", expanded)  # N/STRACCETTI → N / STRACCETTI

            # 3. Clean product name (title-case, normalize units)
            cleaned = ProductMatcher.clean_product_name(
                expanded, detected_brand, strip_brand=False
            )

            # 4. Set brand if detected (and not already set)
            if detected_brand and not ghost.brand:
                ghost.brand = detected_brand

            # 5. Try to detect brand from full name if still no brand
            if not ghost.brand:
                words = cleaned.strip().split()
                for n in (3, 2, 1):
                    if len(words) >= n + 1:
                        candidate = " ".join(words[:n]).lower()
                        canonical = BRAND_ALIASES.get(candidate)
                        if canonical:
                            ghost.brand = canonical
                            break

            # 6. Try to categorize
            if not ghost.category or ghost.category == "Supermercato":
                cat = ProductMatcher.categorize_by_keywords(cleaned, ghost.brand)
                if cat:
                    ghost.category = cat

            if cleaned != original:
                ghost.name = cleaned
                renamed += 1
                logger.info(
                    "Renamed ghost '%s' -> '%s' [brand=%s]",
                    original, cleaned, ghost.brand or "none",
                )

        if renamed > 0:
            await session.commit()

    logger.info("Ghost name cleanup: %d/%d renamed", renamed, total)
    return {"total": total, "renamed": renamed}
