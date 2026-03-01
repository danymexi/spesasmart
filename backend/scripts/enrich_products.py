"""Enrich products with Gemini AI: category, subcategory, and unit.

Finds products where category IS NULL and sends them in batches to Gemini
for classification. Then backfills unit_reference on offers whose products
now have a unit.

Run from the backend directory:
    PYTHONPATH=. python scripts/enrich_products.py
    PYTHONPATH=. python scripts/enrich_products.py --dry-run
    PYTHONPATH=. python scripts/enrich_products.py --batch-size 10 --sleep 8
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import time

import google.generativeai as genai
from sqlalchemy import select, update

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Valid categories (closed list)
# ---------------------------------------------------------------------------
VALID_CATEGORIES = {
    "Latticini",
    "Frutta e Verdura",
    "Bevande",
    "Carne",
    "Pesce",
    "Surgelati",
    "Dolci e Snack",
    "Igiene Personale",
    "Pulizia Casa",
    "Pasta e Riso",
    "Pane e Cereali",
    "Salumi e Formaggi",
    "Condimenti e Conserve",
    "Uova",
    "Alcolici",
    "Acqua",
    "Caffe e Te",
    "Neonati e Infanzia",
    "Pet Care",
    "Altro",
}

# ---------------------------------------------------------------------------
# Gemini system prompt
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """\
Sei un assistente specializzato nella classificazione di prodotti da supermercato italiano.

Riceverai una lista di prodotti in formato JSON, ciascuno con "id", "name" e "brand".
Per ogni prodotto devi restituire un oggetto JSON con:

- "id" (int) -- lo stesso id ricevuto in input, per il matching.
- "category" (string) -- UNA fra queste categorie (tassativo, scegli la piu appropriata):
  "Latticini", "Frutta e Verdura", "Bevande", "Carne", "Pesce", "Surgelati",
  "Dolci e Snack", "Igiene Personale", "Pulizia Casa", "Pasta e Riso",
  "Pane e Cereali", "Salumi e Formaggi", "Condimenti e Conserve", "Uova",
  "Alcolici", "Acqua", "Caffe e Te", "Neonati e Infanzia", "Pet Care", "Altro".
- "subcategory" (string) -- sottocategoria libera in italiano (es. "Yogurt", \
"Shampoo", "Birra", "Pasta fresca").
- "unit" (string) -- la confezione tipica di questo prodotto come si trova al \
supermercato (es. "500 g", "1 kg", "1 L", "6 x 1.5 L", "200 ml", "1 pz"). \
Se non riesci a determinarlo, usa null.

Restituisci SOLO un JSON array valido. Nessun commento, nessun markdown fence.
"""


def _parse_gemini_json(raw: str) -> list[dict]:
    """Parse JSON from Gemini response, stripping markdown fences if needed."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        cleaned = raw
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        try:
            return json.loads(cleaned.strip())
        except json.JSONDecodeError:
            logger.error("Could not parse Gemini response:\n%s", raw[:2000])
            return []


def _init_gemini_model(api_key: str, model_name: str):
    """Initialise Gemini model (same pattern as pipeline.py)."""
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(
        model_name=model_name,
        system_instruction=SYSTEM_PROMPT,
        generation_config=genai.GenerationConfig(
            temperature=0.1,
            top_p=0.95,
            max_output_tokens=8192,
            response_mime_type="application/json",
        ),
    )


def _infer_unit_reference_from_unit(unit: str | None) -> str | None:
    """Infer unit_reference (kg/l/pz) from a product's unit string."""
    if not unit:
        return None
    u = unit.lower().strip()
    if re.search(r"\b(kg|kilo|gramm|g)\b", u):
        return "kg"
    if re.search(r"\b(l|lt|litro|litri|ml)\b", u):
        return "l"
    if re.search(r"\b(pz|pezzo|pezzi|unit[aà])\b", u):
        return "pz"
    return None


async def enrich_products(
    dry_run: bool = False,
    batch_size: int = 25,
    sleep_seconds: int = 5,
    model_name: str | None = None,
) -> None:
    from app.config import get_settings
    from app.database import async_session
    from app.models.offer import Offer
    from app.models.product import Product

    settings = get_settings()

    if not settings.gemini_api_key:
        logger.error("GEMINI_API_KEY not set. Aborting.")
        return

    gemini_model_name = model_name or settings.gemini_model
    logger.info("Using Gemini model: %s", gemini_model_name)
    model = _init_gemini_model(settings.gemini_api_key, gemini_model_name)

    # ------------------------------------------------------------------
    # Phase 1: Enrich products with category/subcategory/unit
    # ------------------------------------------------------------------
    async with async_session() as session:
        result = await session.execute(
            select(
                Product.id,
                Product.name,
                Product.brand,
                Product.category,
                Product.subcategory,
                Product.unit,
            ).where(Product.category.is_(None))
        )
        products = result.all()
        logger.info("Found %d products with category=NULL.", len(products))

        if not products:
            logger.info("Nothing to enrich.")
            return

        # Process in batches
        enriched_count = 0
        total_batches = (len(products) + batch_size - 1) // batch_size

        for batch_idx in range(total_batches):
            start = batch_idx * batch_size
            batch = products[start : start + batch_size]

            # Build input payload (use sequential int ids for matching)
            payload = []
            id_map = {}  # local_idx -> row (id, name, brand, category, subcategory, unit)
            for local_idx, row in enumerate(batch):
                payload.append({
                    "id": local_idx,
                    "name": row.name,
                    "brand": row.brand or "",
                })
                id_map[local_idx] = row

            logger.info(
                "Batch %d/%d: sending %d products to Gemini...",
                batch_idx + 1, total_batches, len(payload),
            )

            if dry_run:
                for item in payload:
                    logger.info(
                        "  [dry-run] id=%d name='%s' brand='%s'",
                        item["id"], item["name"][:60], item["brand"],
                    )
                continue

            # Call Gemini
            user_prompt = json.dumps(payload, ensure_ascii=False)
            try:
                response = await model.generate_content_async(user_prompt)
                raw_json = response.text.strip()
            except Exception:
                logger.exception(
                    "Gemini API call failed for batch %d. Skipping.",
                    batch_idx + 1,
                )
                if batch_idx < total_batches - 1:
                    time.sleep(sleep_seconds)
                continue

            items = _parse_gemini_json(raw_json)
            if not isinstance(items, list):
                logger.error("Gemini returned non-list for batch %d. Skipping.", batch_idx + 1)
                if batch_idx < total_batches - 1:
                    time.sleep(sleep_seconds)
                continue

            # Apply results via UPDATE statements
            for item in items:
                if not isinstance(item, dict):
                    continue
                local_id = item.get("id")
                if local_id is None or local_id not in id_map:
                    continue

                row = id_map[local_id]
                category = (item.get("category") or "").strip()
                subcategory = (item.get("subcategory") or "").strip() or None
                unit = (item.get("unit") or "").strip() or None

                if category and category not in VALID_CATEGORIES:
                    logger.warning(
                        "Category '%s' not in valid list for product '%s'. Accepting anyway.",
                        category, row.name[:50],
                    )

                # Build update values (only NULL fields)
                values = {}
                if row.category is None and category:
                    values["category"] = category
                if row.subcategory is None and subcategory:
                    values["subcategory"] = subcategory
                if row.unit is None and unit:
                    values["unit"] = unit

                if values:
                    await session.execute(
                        update(Product)
                        .where(Product.id == row.id)
                        .values(**values)
                    )
                    enriched_count += 1

            logger.info(
                "Batch %d/%d: enriched %d products so far.",
                batch_idx + 1, total_batches, enriched_count,
            )

            # Rate-limit sleep between batches
            if batch_idx < total_batches - 1:
                time.sleep(sleep_seconds)

        if not dry_run:
            await session.commit()
            logger.info("Committed %d enriched products.", enriched_count)

    # ------------------------------------------------------------------
    # Phase 2: Backfill unit_reference on offers
    # ------------------------------------------------------------------
    if dry_run:
        logger.info("[dry-run] Skipping offer backfill.")
        return

    async with async_session() as session:
        result = await session.execute(
            select(
                Offer.id,
                Product.unit,
            )
            .join(Product, Offer.product_id == Product.id)
            .where(
                Offer.unit_reference.is_(None),
                Product.unit.isnot(None),
                Offer.price_per_unit.isnot(None),
            )
        )
        rows = result.all()
        logger.info("Found %d offers to backfill unit_reference.", len(rows))

        updated = 0
        for offer_id, product_unit in rows:
            unit_ref = _infer_unit_reference_from_unit(product_unit)
            if unit_ref:
                await session.execute(
                    update(Offer)
                    .where(Offer.id == offer_id)
                    .values(unit_reference=unit_ref)
                )
                updated += 1

        await session.commit()
        logger.info("Backfilled unit_reference on %d offers.", updated)


def main():
    parser = argparse.ArgumentParser(
        description="Enrich products with Gemini AI (category, subcategory, unit)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without modifying the DB.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=25,
        help="Number of products per Gemini API call (default: 25).",
    )
    parser.add_argument(
        "--sleep",
        type=int,
        default=5,
        help="Seconds to wait between API calls (default: 5).",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Gemini model to use (default: from settings, usually gemini-2.0-flash).",
    )
    args = parser.parse_args()

    asyncio.run(
        enrich_products(
            dry_run=args.dry_run,
            model_name=args.model,
            batch_size=args.batch_size,
            sleep_seconds=args.sleep,
        )
    )


if __name__ == "__main__":
    main()
