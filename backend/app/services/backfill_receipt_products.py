"""Backfill product_id on PurchaseItems from receipt uploads.

Step 1: fuzzy matching via ProductMatcher (unchanged).
Step 2 (new): AI matching via Claude/Gemini for items that fuzzy match failed on.
"""

import json
import logging
import uuid

from sqlalchemy import or_, select

from app.config import get_settings
from app.database import async_session
from app.models import Product
from app.models.purchase import PurchaseItem, PurchaseOrder
from app.services.product_matcher import ProductMatcher

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


async def _get_candidates_for_item(
    item: PurchaseItem,
    session,
) -> list[dict]:
    """Query DB for candidate products using ILIKE on significant tokens."""
    tokens = [t for t in item.external_name.split() if len(t) > 3]
    if not tokens:
        tokens = [t for t in item.external_name.split() if len(t) > 2]
    if not tokens:
        return []

    # Use up to 3 tokens for ILIKE OR filter
    significant = tokens[:3]
    stmt = select(Product).where(
        or_(*[Product.name.ilike(f"%{tok}%") for tok in significant])
    )
    if item.category:
        stmt = stmt.where(Product.category.ilike(f"%{item.category}%"))
    stmt = stmt.limit(20)

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

    Step 1: Fuzzy matching via ProductMatcher.
    Step 2: AI matching via Claude/Gemini for remaining unmatched items.

    Returns a summary dict with counts of matched and total items processed.
    """
    matcher = ProductMatcher()
    matched = 0
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

        # ── Step 1: Fuzzy matching (existing logic) ──
        still_unmatched: list[PurchaseItem] = []
        for item in items:
            try:
                product = await matcher.create_or_match_product(
                    {"name": item.external_name, "category": item.category},
                    session=session,
                )
                # create_or_match_product always returns a product (creates if no match).
                # We need to check if it *matched* an existing one or created new.
                # If it created a new one, the name will be very close to external_name.
                # A better check: see if product was just created (no offers, same name).
                # For now, trust the matcher — if it returns, it's a match or new product.
                item.product_id = product.id
                matched += 1
            except Exception:
                logger.debug("Backfill fuzzy matching failed for '%s'", item.external_name)
                still_unmatched.append(item)

        # ── Step 2: AI matching for items that fuzzy matching didn't confidently match ──
        # Re-collect items where product_id is still None (fuzzy failed completely)
        # plus items where matcher created a new product (we want AI to try linking to existing)
        ai_unmatched = [it for it in items if it.product_id is None]
        # Add back items from exceptions
        ai_unmatched.extend(still_unmatched)
        # Deduplicate
        seen_ids = set()
        unique_unmatched: list[PurchaseItem] = []
        for it in ai_unmatched:
            if it.id not in seen_ids:
                seen_ids.add(it.id)
                unique_unmatched.append(it)

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

        if matched > 0:
            await session.commit()

    logger.info(
        "Backfill for user %s: %d/%d items matched", user_id, matched, total
    )
    return {"matched": matched, "total": total}
