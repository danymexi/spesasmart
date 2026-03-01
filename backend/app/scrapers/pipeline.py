"""OCR + Gemini AI extraction pipeline for flyer images.

Workflow:
    1. Receive a flyer page image.
    2. Send the image directly to Gemini Vision to extract structured product data.
    3. Persist results to the database.

Uses Gemini Vision (multimodal) as a single step, eliminating the need for
a separate Google Cloud Vision OCR service account.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import google.generativeai as genai

from app.config import get_settings
from app.database import async_session
from app.models.flyer import Flyer, FlyerPage
from app.models.offer import Offer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Gemini system prompt -- instructs the model to parse Italian supermarket
# flyer images and return structured JSON.
# ---------------------------------------------------------------------------
GEMINI_SYSTEM_PROMPT = """\
You are a specialised data-extraction assistant for Italian supermarket flyers.

You will receive an image of a single page from a promotional flyer published \
by an Italian supermarket chain (the chain name is provided).

Your task is to identify every distinct product offer on that page and return \
a JSON **array** of objects.  Each object MUST contain exactly the following \
keys (use ``null`` when the value cannot be determined):

- "name"           (string)  -- product name as printed (Italian).
- "brand"          (string | null) -- brand name if identifiable.
- "category"       (string | null) -- broad product category in Italian \
  (e.g. "Latticini", "Frutta e Verdura", "Bevande", "Carne", "Surgelati", \
  "Dolci", "Igiene personale", "Pulizia casa", "Pasta e Riso").
- "original_price" (string | null) -- original (barred / crossed-out) price, \
  as printed.  Italian format with comma as decimal separator, e.g. "3,49".
- "offer_price"    (string) -- promotional / discounted price, as printed.  \
  Same format, e.g. "2,29".
- "discount_pct"   (string | null) -- discount percentage if shown, e.g. "30%".
- "discount_type"  (string | null) -- one of: "percentage", "multi_buy", \
  "loyalty_card", "coupon", "clearance", "other", or null.
- "quantity"       (string | null) -- pack size / weight as printed, \
  e.g. "500 g", "6 x 1,5 L", "1 kg".
- "price_per_unit" (string | null) -- price per kg/L/unit if printed.
- "unit_reference" (string | null) -- the unit for price_per_unit: "kg", "l", or "pz".
- "raw_text"       (string) -- the text visible on the flyer for this product \
  (for traceability).
- "confidence"     (number) -- your confidence in the extraction, 0.0 to 1.0.

IMPORTANT RULES:
1. Return ONLY valid JSON -- no markdown fences, no commentary.
2. If the page contains no product offers (e.g. it is a cover or index page), \
   return an empty array ``[]``.
3. Prices MUST stay in Italian format (comma as decimal separator) as they \
   appear on the flyer.  Do NOT convert them.
4. Do NOT invent data.  If something is unclear, set the field to null and \
   lower the confidence.
5. The array must be parseable by ``json.loads`` in Python.
"""

# Alternate prompt for text-only input (fallback when image cannot be sent)
GEMINI_TEXT_PROMPT = GEMINI_SYSTEM_PROMPT.replace(
    "You will receive an image of a single page",
    "You will receive raw OCR text extracted from a single page",
)


class ScrapingPipeline:
    """Orchestrates Gemini Vision extraction for flyer page images."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._gemini_model = None
        self._gemini_text_model = None

    # ------------------------------------------------------------------
    # Lazy initialisation
    # ------------------------------------------------------------------

    def _get_gemini_model(self):
        """Gemini model configured for image+text (Vision) input."""
        if self._gemini_model is None:
            genai.configure(api_key=self.settings.gemini_api_key)
            self._gemini_model = genai.GenerativeModel(
                model_name=self.settings.gemini_model,
                system_instruction=GEMINI_SYSTEM_PROMPT,
                generation_config=genai.GenerationConfig(
                    temperature=0.1,
                    top_p=0.95,
                    max_output_tokens=8192,
                    response_mime_type="application/json",
                ),
            )
        return self._gemini_model

    def _get_gemini_text_model(self):
        """Gemini model configured for text-only input (fallback)."""
        if self._gemini_text_model is None:
            genai.configure(api_key=self.settings.gemini_api_key)
            self._gemini_text_model = genai.GenerativeModel(
                model_name=self.settings.gemini_model,
                system_instruction=GEMINI_TEXT_PROMPT,
                generation_config=genai.GenerationConfig(
                    temperature=0.1,
                    top_p=0.95,
                    max_output_tokens=8192,
                    response_mime_type="application/json",
                ),
            )
        return self._gemini_text_model

    # ------------------------------------------------------------------
    # Gemini Vision -- image directly to Gemini (no separate OCR)
    # ------------------------------------------------------------------

    async def gemini_vision_extract(
        self,
        image_path: str | Path,
        chain_name: str,
    ) -> list[dict[str, Any]]:
        """Send an image directly to Gemini Vision and return product dicts.

        This replaces the Google Cloud Vision OCR + Gemini text pipeline
        with a single multimodal Gemini call.
        """
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        model = self._get_gemini_model()

        # Upload the image as inline data
        image_data = image_path.read_bytes()
        mime_type = "image/png"
        if image_path.suffix.lower() in (".jpg", ".jpeg"):
            mime_type = "image/jpeg"
        elif image_path.suffix.lower() == ".webp":
            mime_type = "image/webp"

        image_part = {"mime_type": mime_type, "data": image_data}
        user_prompt = f"Supermarket chain: {chain_name}\n\nExtract all product offers from this flyer page."

        try:
            response = await model.generate_content_async([user_prompt, image_part])
            raw_json = response.text.strip()
        except Exception:
            logger.exception("Gemini Vision API call failed for %s", image_path.name)
            return []

        return self._parse_gemini_json(raw_json, chain_name)

    # ------------------------------------------------------------------
    # Text-only fallback (when OCR text is already available)
    # ------------------------------------------------------------------

    async def gemini_extract_from_text(
        self,
        ocr_text: str,
        chain_name: str,
    ) -> list[dict[str, Any]]:
        """Send OCR text to Gemini and return structured product dicts."""
        if not ocr_text.strip():
            logger.info("Empty OCR text -- skipping Gemini call.")
            return []

        model = self._get_gemini_text_model()
        user_prompt = (
            f"Supermarket chain: {chain_name}\n\n"
            f"--- OCR TEXT START ---\n{ocr_text}\n--- OCR TEXT END ---"
        )

        try:
            response = await model.generate_content_async(user_prompt)
            raw_json = response.text.strip()
        except Exception:
            logger.exception("Gemini text API call failed for chain=%s", chain_name)
            return []

        return self._parse_gemini_json(raw_json, chain_name)

    # ------------------------------------------------------------------
    # Process a single flyer page
    # ------------------------------------------------------------------

    async def process_flyer_page(
        self,
        image_path: str | Path,
        chain_name: str,
    ) -> list[dict[str, Any]]:
        """Run the Gemini Vision pipeline for one page image.

        Returns the list of extracted product dicts.
        """
        image_path = Path(image_path)
        logger.info("Processing flyer page: %s (chain=%s)", image_path.name, chain_name)
        products = await self.gemini_vision_extract(image_path, chain_name)
        return products

    # ------------------------------------------------------------------
    # Process entire flyer and persist to DB
    # ------------------------------------------------------------------

    async def process_flyer(
        self,
        flyer_id: uuid.UUID,
        image_paths: list[str | Path],
        chain_name: str,
        chain_id: uuid.UUID,
        store_id: uuid.UUID | None = None,
        valid_from=None,
        valid_to=None,
    ) -> int:
        """Process all pages of a flyer and save extracted offers to the DB.

        Returns the total number of offers persisted.
        """
        total_saved = 0

        async with async_session() as session:
            for page_number, img_path in enumerate(image_paths, start=1):
                img_path = Path(img_path)

                # --- Gemini Vision extraction --------------------------
                try:
                    products = await self.process_flyer_page(img_path, chain_name)
                except Exception:
                    logger.exception(
                        "Pipeline failed for page %d of flyer %s",
                        page_number,
                        flyer_id,
                    )
                    products = []

                # --- Create FlyerPage row ------------------------------
                page_row = FlyerPage(
                    flyer_id=flyer_id,
                    page_number=page_number,
                    image_url=str(img_path),
                    ocr_raw_text=None,  # OCR text not used in Vision mode
                    processed=True,
                )
                session.add(page_row)

                # --- Persist each product + offer ----------------------
                for prod_data in products:
                    try:
                        offer_count = await self._save_product_offer(
                            session=session,
                            prod_data=prod_data,
                            flyer_id=flyer_id,
                            chain_id=chain_id,
                            store_id=store_id,
                            valid_from=valid_from,
                            valid_to=valid_to,
                        )
                        total_saved += offer_count
                    except Exception:
                        logger.exception(
                            "Failed to save product: %s",
                            prod_data.get("name", "<unknown>"),
                        )

            # Mark flyer as processed.
            flyer = await session.get(Flyer, flyer_id)
            if flyer is not None:
                flyer.status = "processed"
                flyer.pages_count = len(image_paths)

            await session.commit()

        logger.info(
            "Flyer %s fully processed: %d offers saved from %d pages.",
            flyer_id,
            total_saved,
            len(image_paths),
        )
        return total_saved

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_gemini_json(self, raw_json: str, chain_name: str) -> list[dict[str, Any]]:
        """Parse the JSON response from Gemini."""
        try:
            products = json.loads(raw_json)
        except json.JSONDecodeError:
            # Sometimes the model wraps in markdown code fences -- strip them.
            cleaned = raw_json
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("```", 1)[0]
            try:
                products = json.loads(cleaned.strip())
            except json.JSONDecodeError:
                logger.error(
                    "Could not parse Gemini response as JSON:\n%s",
                    raw_json[:2000],
                )
                return []

        if not isinstance(products, list):
            logger.error("Gemini returned a non-list type: %s", type(products))
            return []

        logger.info(
            "Gemini extracted %d products for chain=%s",
            len(products),
            chain_name,
        )
        return products

    @staticmethod
    def _parse_italian_price(raw: str | None) -> Decimal | None:
        """Convert an Italian-format price string to ``Decimal``.

        Examples: ``"3,49"`` -> ``Decimal("3.49")``
        """
        if not raw:
            return None
        text = raw.strip().replace("\u20ac", "").replace("euro", "").strip()
        # Italian: comma is decimal separator, dot is thousands.
        text = text.replace(".", "").replace(",", ".")
        # Keep only digits and dot.
        text = re.sub(r"[^\d.]", "", text)
        if not text:
            return None
        try:
            return Decimal(text)
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def parse_italian_price(raw: str | None) -> Decimal | None:
        """Public alias for _parse_italian_price (used in tests)."""
        return ScrapingPipeline._parse_italian_price(raw)

    @staticmethod
    def _parse_confidence(raw) -> Decimal | None:
        """Safely convert a confidence value to Decimal."""
        if raw is None:
            return None
        try:
            val = Decimal(str(raw))
            if val < 0:
                val = Decimal("0")
            elif val > 1:
                val = Decimal("1")
            return val
        except (InvalidOperation, ValueError, TypeError):
            return None

    @staticmethod
    def validate_product_data(data: dict) -> bool:
        """Check that a product dict has the minimum required fields."""
        return bool(data.get("name")) and data.get("offer_price") is not None

    @staticmethod
    def _infer_unit_reference(quantity: str | None, raw_text: str | None) -> str | None:
        """Infer unit_reference from quantity or raw_text via regex."""
        for text in (quantity, raw_text):
            if not text:
                continue
            if re.search(r"(?:al\s+kg|/kg|euro/kg|eur/kg)", text, re.IGNORECASE):
                return "kg"
            if re.search(r"(?:al\s+l(?:t|itro)?|/l\b|euro/l|eur/l)", text, re.IGNORECASE):
                return "l"
            if re.search(r"(?:al\s+pz|/pz|cadauno|cad\.)", text, re.IGNORECASE):
                return "pz"
        return None

    @staticmethod
    def clean_product_name(name: str) -> str:
        """Normalize whitespace and casing of a product name."""
        cleaned = " ".join(name.split())
        return cleaned.title() if cleaned == cleaned.upper() or cleaned == cleaned.lower() else cleaned

    async def _save_product_offer(
        self,
        *,
        session,
        prod_data: dict[str, Any],
        flyer_id: uuid.UUID,
        chain_id: uuid.UUID,
        store_id: uuid.UUID | None,
        valid_from,
        valid_to,
    ) -> int:
        """Create or match a Product row and attach an Offer.

        Returns 1 on success, 0 on skip.
        """
        name = (prod_data.get("name") or "").strip()
        if not name:
            return 0

        offer_price = self._parse_italian_price(prod_data.get("offer_price"))
        if offer_price is None:
            logger.debug("Skipping product without parseable offer_price: %s", name)
            return 0

        # Find or create product (fuzzy dedup via ProductMatcher)
        brand = (prod_data.get("brand") or "").strip() or None
        from app.services.product_matcher import ProductMatcher

        matcher = ProductMatcher()
        product = await matcher.create_or_match_product(
            {
                "name": name,
                "brand": brand,
                "category": (prod_data.get("category") or "").strip() or None,
                "unit": prod_data.get("quantity"),
            },
            session=session,
        )

        # Build the Offer row.
        original_price = self._parse_italian_price(prod_data.get("original_price"))
        discount_pct_str = prod_data.get("discount_pct")
        discount_pct: Decimal | None = None
        if discount_pct_str:
            match = re.search(r"(\d+(?:[.,]\d+)?)", str(discount_pct_str))
            if match:
                try:
                    discount_pct = Decimal(match.group(1).replace(",", "."))
                except (InvalidOperation, ValueError):
                    pass

        price_per_unit = self._parse_italian_price(prod_data.get("price_per_unit"))

        # Determine unit_reference from Gemini output or fallback regex
        unit_reference = prod_data.get("unit_reference")
        if not unit_reference:
            unit_reference = self._infer_unit_reference(
                prod_data.get("quantity"), prod_data.get("raw_text")
            )

        offer = Offer(
            product_id=product.id,
            flyer_id=flyer_id,
            chain_id=chain_id,
            store_id=store_id,
            original_price=original_price,
            offer_price=offer_price,
            discount_pct=discount_pct,
            discount_type=prod_data.get("discount_type"),
            quantity=prod_data.get("quantity"),
            price_per_unit=price_per_unit,
            unit_reference=unit_reference,
            valid_from=valid_from,
            valid_to=valid_to,
            raw_text=prod_data.get("raw_text"),
            confidence=self._parse_confidence(prod_data.get("confidence")),
        )
        session.add(offer)
        return 1
