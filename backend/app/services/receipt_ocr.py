"""OCR service for supermarket receipts.

Primary: Claude (Anthropic) — handles both images and text.
Fallback: Gemini — used only if Anthropic key is not configured.
For PDFs: extracts text with pdfplumber, sends text to the AI model.
For images: sends directly via vision capabilities.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

RECEIPT_SYSTEM_PROMPT = """\
You are a specialised data-extraction assistant for Italian supermarket receipts \
(scontrini).

You will receive either a photo or the raw text of a receipt from an Italian \
supermarket (the chain name is provided).

Your task is to extract ALL information and return a single JSON **object** with \
the following keys:

- "store_name"    (string | null) — name or location of the store as printed.
- "store_address" (string | null) — address of the store if visible.
- "date"          (string | null) — date of the purchase in ISO format YYYY-MM-DD.  \
  If only day/month are visible, assume the current year.
- "time"          (string | null) — time of purchase in HH:MM format if visible.
- "total"         (string | null) — total amount paid, Italian format with comma \
  as decimal separator, e.g. "45,30".
- "items"         (array) — list of purchased items, each an object with:
    - "name"        (string) — product name **expanded to a readable form**.  \
      Receipt names are often truncated or abbreviated (e.g. "YOG.GRECO MUL." → \
      "Yogurt Greco Muller", "SACC.COMPOST." → "Sacchetto Compostabile", \
      "MOZZ.BUF.CAMP." → "Mozzarella di Bufala Campana").  Expand abbreviations \
      when the meaning is clear.  Use Title Case.
    - "quantity"    (number) — quantity purchased (default 1 if not printed).
    - "unit_price"  (string | null) — unit price in Italian format, e.g. "2,49".
    - "total_price" (string) — line total in Italian format, e.g. "4,98".
    - "discount"    (string | null) — any discount applied to this line, e.g. "-0,50".
    - "category"    (string | null) — broad category in Italian if identifiable \
      (e.g. "Latticini", "Frutta e Verdura", "Bevande", "Carne", "Surgelati", \
      "Dolci", "Igiene personale", "Pulizia casa", "Pasta e Riso", "Pane").
    - "is_product"  (boolean) — true if this line is an actual purchased product.  \
      Set to false for non-product lines such as: bags (sacchetti, buste, \
      shopper), deposit/cauzione, coupons/buoni, loyalty points, subtotals, \
      payment lines, cashback, rounding adjustments, VAT lines, or any \
      other line that is NOT a product the customer intended to buy.

IMPORTANT RULES:
1. Return ONLY valid JSON — no markdown fences, no commentary.
2. Prices MUST stay in Italian format (comma as decimal separator) as they \
   appear on the receipt.  Do NOT convert them.
3. Do NOT invent data.  If something is unclear, set the field to null.
4. Include ALL lines from the receipt in "items" but mark non-products with \
   "is_product": false so they can be filtered downstream.
5. The JSON must be parseable by ``json.loads`` in Python.
6. Expand abbreviated names to their full readable form whenever possible.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_italian_price(raw: str | None) -> Decimal | None:
    """Convert an Italian-format price string to Decimal."""
    if not raw:
        return None
    text = raw.strip().replace("\u20ac", "").replace("euro", "").strip()
    text = text.replace(".", "").replace(",", ".")
    text = re.sub(r"[^\d.\-]", "", text)
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _parse_json_response(raw_json: str) -> dict[str, Any]:
    """Parse AI JSON response, handling markdown fences."""
    try:
        return json.loads(raw_json)
    except json.JSONDecodeError:
        cleaned = raw_json
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        try:
            return json.loads(cleaned.strip())
        except json.JSONDecodeError:
            logger.error("Could not parse AI receipt response:\n%s", raw_json[:2000])
            return {}


def _extract_pdf_text(pdf_path: Path) -> str:
    """Extract text from all pages of a PDF using pdfplumber."""
    try:
        import pdfplumber
    except ImportError:
        logger.error("pdfplumber is not installed.")
        return ""

    pages_text = []
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)
    except Exception:
        logger.exception("Failed to extract text from PDF: %s", pdf_path)
        return ""

    combined = "\n\n".join(pages_text)
    logger.info(
        "Extracted %d chars from %d pages of %s",
        len(combined), len(pages_text), pdf_path.name,
    )
    return combined


# ---------------------------------------------------------------------------
# Claude (Anthropic) provider
# ---------------------------------------------------------------------------

async def _parse_with_claude(
    image_path: Path,
    chain_label: str,
    pdf_text: str | None,
) -> dict[str, Any]:
    """Use Claude API for receipt parsing (text or vision)."""
    import anthropic

    settings = get_settings()
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    messages_content: list[dict[str, Any]] = []

    if pdf_text:
        # Text-only: send extracted PDF text
        messages_content.append({
            "type": "text",
            "text": (
                f"Supermarket chain: {chain_label}\n\n"
                f"--- RECEIPT TEXT START ---\n{pdf_text}\n--- RECEIPT TEXT END ---"
            ),
        })
    else:
        # Image: send as base64 via vision
        file_data = image_path.read_bytes()
        suffix = image_path.suffix.lower()
        mime_map = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".webp": "image/webp", ".png": "image/png",
        }
        mime_type = mime_map.get(suffix, "image/jpeg")
        b64_data = base64.b64encode(file_data).decode("utf-8")

        messages_content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": mime_type,
                "data": b64_data,
            },
        })
        messages_content.append({
            "type": "text",
            "text": (
                f"Supermarket chain: {chain_label}\n\n"
                "Extract all data from this receipt."
            ),
        })

    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=8192,
        temperature=0.1,
        system=RECEIPT_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": messages_content}],
    )

    raw_json = response.content[0].text.strip()
    return _parse_json_response(raw_json)


# ---------------------------------------------------------------------------
# Gemini provider (fallback)
# ---------------------------------------------------------------------------

async def _parse_with_gemini(
    image_path: Path,
    chain_label: str,
    pdf_text: str | None,
) -> dict[str, Any]:
    """Use Gemini API for receipt parsing (text or vision)."""
    import google.generativeai as genai

    settings = get_settings()
    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(
        model_name=settings.gemini_model,
        system_instruction=RECEIPT_SYSTEM_PROMPT,
        generation_config=genai.GenerationConfig(
            temperature=0.1,
            top_p=0.95,
            max_output_tokens=8192,
            response_mime_type="application/json",
        ),
    )

    if pdf_text:
        user_prompt = (
            f"Supermarket chain: {chain_label}\n\n"
            f"--- RECEIPT TEXT START ---\n{pdf_text}\n--- RECEIPT TEXT END ---"
        )
        response = await model.generate_content_async(user_prompt)
    else:
        file_data = image_path.read_bytes()
        suffix = image_path.suffix.lower()
        mime_map = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".webp": "image/webp", ".png": "image/png",
        }
        mime_type = mime_map.get(suffix, "image/jpeg")
        file_part = {"mime_type": mime_type, "data": file_data}
        user_prompt = (
            f"Supermarket chain: {chain_label}\n\n"
            "Extract all data from this receipt."
        )
        response = await model.generate_content_async([user_prompt, file_part])

    raw_json = response.text.strip()
    return _parse_json_response(raw_json)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def parse_receipt_image(
    image_path: str | Path,
    chain_slug: str,
) -> dict[str, Any]:
    """Parse a receipt file (image or PDF) and return structured data.

    Tries Claude first (if API key configured), falls back to Gemini.
    For PDFs: extracts text with pdfplumber before sending to the AI model.
    """
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"File not found: {image_path}")

    chain_label = chain_slug.capitalize()

    # For PDFs, extract text upfront (shared by both providers)
    pdf_text: str | None = None
    if image_path.suffix.lower() == ".pdf":
        pdf_text = _extract_pdf_text(image_path)
        if not pdf_text.strip():
            return {"error": "Nessun testo trovato nel PDF.", "items": []}

    settings = get_settings()

    # Try Claude first
    if settings.anthropic_api_key:
        try:
            result = await _parse_with_claude(image_path, chain_label, pdf_text)
            if isinstance(result, dict) and result:
                if "items" not in result:
                    result["items"] = []
                logger.info(
                    "Receipt parsed (Claude): chain=%s, store=%s, items=%d, total=%s",
                    chain_slug, result.get("store_name"),
                    len(result.get("items", [])), result.get("total"),
                )
                return result
        except Exception:
            logger.exception("Claude API call failed for receipt %s, trying Gemini...", image_path.name)

    # Fallback to Gemini
    if settings.gemini_api_key:
        try:
            result = await _parse_with_gemini(image_path, chain_label, pdf_text)
            if isinstance(result, dict) and result:
                if "items" not in result:
                    result["items"] = []
                logger.info(
                    "Receipt parsed (Gemini): chain=%s, store=%s, items=%d, total=%s",
                    chain_slug, result.get("store_name"),
                    len(result.get("items", [])), result.get("total"),
                )
                return result
        except Exception:
            logger.exception("Gemini API call failed for receipt %s", image_path.name)

    return {"error": "Nessun provider AI disponibile o tutti hanno fallito.", "items": []}
