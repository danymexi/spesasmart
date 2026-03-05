"""Enrich products with AI: category, subcategory, and unit.

Supports both Claude (Anthropic) and Gemini (Google) as AI backends.
Finds products where category IS NULL or 'Supermercato' (generic) and sends
them in batches for classification. Then backfills unit_reference on offers.

Run from the backend directory:
    PYTHONPATH=. python scripts/enrich_products.py --target supermercato
    PYTHONPATH=. python scripts/enrich_products.py --target supermercato --provider claude
    PYTHONPATH=. python scripts/enrich_products.py --dry-run --target all
    PYTHONPATH=. python scripts/enrich_products.py --batch-size 50 --sleep 2 --provider claude
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import time

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
    "Gastronomia",
    "Benessere e Intolleranze",
    "Altro",
}

_CATEGORIES_STR = ", ".join(f'"{c}"' for c in sorted(VALID_CATEGORIES))

# Categories considered "generic" — products with these get re-classified
_GENERIC_CATEGORIES = {"Supermercato", None}

# ---------------------------------------------------------------------------
# System prompt (shared across providers)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = f"""\
Sei un assistente specializzato nella classificazione di prodotti da supermercato italiano.

Riceverai una lista di prodotti in formato JSON, ciascuno con "id", "name" e "brand".
Per ogni prodotto devi restituire un oggetto JSON con:

- "id" (int) -- lo stesso id ricevuto in input, per il matching.
- "category" (string) -- UNA fra queste categorie (tassativo, scegli la piu appropriata):
  {_CATEGORIES_STR}.
- "subcategory" (string) -- sottocategoria libera in italiano (es. "Yogurt", \
"Shampoo", "Birra", "Pasta fresca").
- "unit" (string) -- la confezione tipica di questo prodotto come si trova al \
supermercato (es. "500 g", "1 kg", "1 L", "6 x 1.5 L", "200 ml", "1 pz"). \
Se non riesci a determinarlo, usa null.

Restituisci SOLO un JSON array valido. Nessun commento, nessun markdown fence."""


# ---------------------------------------------------------------------------
# AI Provider abstraction
# ---------------------------------------------------------------------------

class AIProvider:
    """Base class for AI providers."""
    async def classify(self, payload_json: str) -> str:
        raise NotImplementedError


class ClaudeProvider(AIProvider):
    """Anthropic Claude provider."""

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001"):
        import anthropic
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = model

    async def classify(self, payload_json: str) -> str:
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=8192,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": payload_json}],
        )
        return response.content[0].text


class GeminiProvider(AIProvider):
    """Google Gemini provider."""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(
            model_name=model,
            system_instruction=SYSTEM_PROMPT,
            generation_config=genai.GenerationConfig(
                temperature=0.1,
                top_p=0.95,
                max_output_tokens=8192,
                response_mime_type="application/json",
            ),
        )

    async def classify(self, payload_json: str) -> str:
        response = await self.model.generate_content_async(payload_json)
        return response.text.strip()


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------

def _parse_json_response(raw: str) -> list[dict]:
    """Parse JSON from AI response, stripping markdown fences if needed."""
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
            logger.error("Could not parse AI response:\n%s", raw[:2000])
            return []


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


# ---------------------------------------------------------------------------
# Main enrichment logic
# ---------------------------------------------------------------------------

async def enrich_products(
    dry_run: bool = False,
    batch_size: int = 25,
    sleep_seconds: int = 5,
    model_name: str | None = None,
    target: str = "null",
    provider_name: str = "claude",
) -> None:
    from app.config import get_settings
    from app.database import async_session
    from app.models.offer import Offer
    from app.models.product import Product

    settings = get_settings()

    # Initialise AI provider
    if provider_name == "claude":
        api_key = settings.anthropic_api_key
        if not api_key:
            logger.error("ANTHROPIC_API_KEY not set. Aborting.")
            return
        model = model_name or "claude-haiku-4-5-20251001"
        provider = ClaudeProvider(api_key, model)
        logger.info("Using Claude model: %s", model)
    else:
        api_key = settings.gemini_api_key
        if not api_key:
            logger.error("GEMINI_API_KEY not set. Aborting.")
            return
        model = model_name or settings.gemini_model
        provider = GeminiProvider(api_key, model)
        logger.info("Using Gemini model: %s", model)

    # ------------------------------------------------------------------
    # Phase 1: Enrich products with category/subcategory/unit
    # ------------------------------------------------------------------
    async with async_session() as session:
        base_query = select(
            Product.id,
            Product.name,
            Product.brand,
            Product.category,
            Product.subcategory,
            Product.unit,
        )

        if target == "supermercato":
            query = base_query.where(Product.category == "Supermercato")
        elif target == "all":
            from sqlalchemy import or_
            query = base_query.where(
                or_(Product.category.is_(None), Product.category == "Supermercato")
            )
        else:  # "null"
            query = base_query.where(Product.category.is_(None))

        result = await session.execute(query)
        products = result.all()
        logger.info("Found %d products to enrich (target=%s).", len(products), target)

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
            id_map = {}
            for local_idx, row in enumerate(batch):
                payload.append({
                    "id": local_idx,
                    "name": row.name,
                    "brand": row.brand or "",
                })
                id_map[local_idx] = row

            logger.info(
                "Batch %d/%d: sending %d products to %s...",
                batch_idx + 1, total_batches, len(payload), provider_name,
            )

            if dry_run:
                for item in payload:
                    logger.info(
                        "  [dry-run] id=%d name='%s' brand='%s'",
                        item["id"], item["name"][:60], item["brand"],
                    )
                continue

            # Call AI provider
            user_prompt = json.dumps(payload, ensure_ascii=False)
            try:
                raw_json = await provider.classify(user_prompt)
            except Exception:
                logger.exception(
                    "AI call failed for batch %d. Skipping.",
                    batch_idx + 1,
                )
                if batch_idx < total_batches - 1:
                    time.sleep(sleep_seconds)
                continue

            items = _parse_json_response(raw_json)
            if not isinstance(items, list):
                logger.error("AI returned non-list for batch %d. Skipping.", batch_idx + 1)
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

                # Build update values (overwrite generic categories)
                values = {}
                if category and (row.category is None or row.category in _GENERIC_CATEGORIES):
                    values["category"] = category
                if subcategory and (row.subcategory is None or row.subcategory in _GENERIC_CATEGORIES):
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
        description="Enrich products with AI (category, subcategory, unit)."
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
        help="Number of products per API call (default: 25).",
    )
    parser.add_argument(
        "--sleep",
        type=int,
        default=2,
        help="Seconds to wait between API calls (default: 2).",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model name (default: claude-haiku-4-5-20251001 for Claude, gemini-2.0-flash for Gemini).",
    )
    parser.add_argument(
        "--target",
        choices=["null", "supermercato", "all"],
        default="null",
        help="Which products to enrich: 'null' (category IS NULL), "
             "'supermercato' (category='Supermercato'), 'all' (both). Default: null.",
    )
    parser.add_argument(
        "--provider",
        choices=["claude", "gemini"],
        default="claude",
        help="AI provider to use (default: claude).",
    )
    args = parser.parse_args()

    asyncio.run(
        enrich_products(
            dry_run=args.dry_run,
            model_name=args.model,
            batch_size=args.batch_size,
            sleep_seconds=args.sleep,
            target=args.target,
            provider_name=args.provider,
        )
    )


if __name__ == "__main__":
    main()
