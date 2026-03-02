"""Unit price calculator service.

Parses Italian quantity strings (e.g. "6 x 1,5 L", "500g", "4 pezzi") and
computes a normalised price-per-unit value so that offers from different chains
can be compared on a fair basis.
"""

import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Unit normalisation maps
# ---------------------------------------------------------------------------

# Weight units -> kilograms
_WEIGHT_UNITS: dict[str, Decimal] = {
    "kg": Decimal("1"),
    "g": Decimal("0.001"),
    "gr": Decimal("0.001"),
    "grammi": Decimal("0.001"),
    "hg": Decimal("0.1"),
    "etto": Decimal("0.1"),
    "etti": Decimal("0.1"),
}

# Volume units -> litres
_VOLUME_UNITS: dict[str, Decimal] = {
    "l": Decimal("1"),
    "lt": Decimal("1"),
    "litri": Decimal("1"),
    "litro": Decimal("1"),
    "ml": Decimal("0.001"),
    "cl": Decimal("0.01"),
    "dl": Decimal("0.1"),
}

# Count units -> per piece
_COUNT_WORDS: set[str] = {
    "pezzi", "pz", "rotoli", "capsule", "bustine", "buste",
    "compresse", "pastiglie", "tabs", "dosi", "porzioni",
    "fette", "stecche", "panetti", "confezioni", "conf",
    "sacchetti", "paia", "unita", "unità",
}

# ---------------------------------------------------------------------------
# Regex patterns (Italian conventions: comma as decimal separator)
# ---------------------------------------------------------------------------

# Multi-pack: "6 x 1,5 L", "6x1.5l", "6 x 200 ml"
_RE_MULTIPACK = re.compile(
    r"(\d+)\s*[xX×]\s*(\d+(?:[.,]\d+)?)\s*(kg|g|gr|hg|l|lt|ml|cl|dl|litri|litro)\b",
    re.IGNORECASE,
)

# Simple quantity with unit: "500g", "1,5 L", "750 ml", "1 kg"
_RE_QTY_UNIT = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(kg|g|gr|grammi|hg|etto|etti|l|lt|litri|litro|ml|cl|dl)\b",
    re.IGNORECASE,
)

# Count: "4 pezzi", "6 rotoli", "10 capsule"
_RE_COUNT = re.compile(
    r"(\d+)\s+(" + "|".join(_COUNT_WORDS) + r")\b",
    re.IGNORECASE,
)

# Plain count at start: "4 " (only when nothing else matches, from product name)
_RE_PLAIN_COUNT = re.compile(
    r"^(\d+)\s*$",
)


def _parse_decimal(s: str) -> Decimal:
    """Parse an Italian-format number string to Decimal."""
    return Decimal(s.replace(",", "."))


# ---------------------------------------------------------------------------
# Keyword lists for inferring kg vs l when scraper says "pz" incorrectly
# ---------------------------------------------------------------------------

_WEIGHT_KEYWORDS: set[str] = {
    "latte", "formaggio", "parmigiano", "grana", "pecorino", "mozzarella",
    "carne", "manzo", "vitello", "maiale", "pollo", "tacchino", "agnello",
    "pasta", "riso", "pane", "farina", "zucchero", "sale",
    "salame", "prosciutto", "bresaola", "mortadella", "speck", "pancetta",
    "burro", "ricotta", "mascarpone", "stracchino", "gorgonzola",
    "nutella", "marmellata", "miele",
    "tonno", "salmone", "pesce", "merluzzo", "gamberi",
    "insalata", "verdura", "frutta", "patate", "pomodori", "cipolle",
    "biscotti", "cereali", "crackers", "grissini",
    "caffe", "caffè", "cacao",
}

_VOLUME_KEYWORDS: set[str] = {
    "acqua", "birra", "vino", "spumante", "prosecco",
    "olio", "aceto",
    "succo", "aranciata", "cola", "sprite", "fanta", "the", "tè", "thè",
    "latte",  # latte is also volume (litri) — handled by checking both
    "detersivo", "ammorbidente", "candeggina", "sgrassatore",
    "shampoo", "bagnoschiuma", "sapone", "balsamo",
    "lacca", "crema", "gel", "schiuma", "mousse",
    "dentifricio", "collutorio", "detergente", "doccia",
    "lozione", "tonico", "siero", "spray", "profumo",
    "deodorante", "conditioner", "maschera",
    "nettare", "sciroppo", "bevanda",
    "liquore", "amaro", "gin", "vodka", "rum", "whisky",
}

# Regex to detect volume/weight units inside a product_unit string like "ml 300", "500 g"
_RE_VOLUME_IN_UNIT = re.compile(r"\b(ml|cl|dl|l|lt|litri|litro)\b", re.IGNORECASE)
_RE_WEIGHT_IN_UNIT = re.compile(r"\b(g|gr|grammi|hg|kg|etto|etti)\b", re.IGNORECASE)


class UnitPriceCalculator:
    """Compute normalised ``(price_per_unit, unit_reference)`` from quantity strings."""

    @staticmethod
    def infer_unit_reference(
        offer_price: Decimal,
        price_per_unit: Decimal,
        product_name: str | None,
        scraper_unit: str | None,
        product_unit: str | None = None,
    ) -> str:
        """Validate and correct the unit_reference provided by a scraper.

        Many scrapers (especially Iperal) report ``"pz"`` for ALL products,
        even when the PPU is clearly per-kg or per-litre.  This method uses
        the product's unit field, a price-ratio heuristic, and product-name
        keywords to infer the real unit.

        Returns one of ``"kg"``, ``"l"``, ``"pz"``.
        """
        if scraper_unit in ("kg", "l"):
            return scraper_unit

        # If PPU <= offer_price, "pz" is plausible (price per piece)
        if (
            scraper_unit == "pz"
            and price_per_unit <= offer_price
        ):
            return "pz"

        # PPU > offer_price * 1.5 → clearly not per-piece, infer kg or l
        if price_per_unit > offer_price * Decimal("1.5"):
            return UnitPriceCalculator._infer_kg_or_l(
                product_name, product_unit
            )

        # PPU between offer_price and offer_price*1.5 → ambiguous, trust scraper
        if scraper_unit:
            return scraper_unit

        return UnitPriceCalculator._infer_kg_or_l(product_name, product_unit)

    @staticmethod
    def _infer_kg_or_l(
        product_name: str | None, product_unit: str | None = None
    ) -> str:
        """Guess whether a product is sold by weight (kg) or volume (l).

        Checks the product's ``unit`` field first (most reliable), then
        falls back to keyword matching on the product name.
        """
        # 1. Check product_unit field (e.g. "ml 300", "500 g", "1 lt")
        if product_unit:
            if _RE_VOLUME_IN_UNIT.search(product_unit):
                return "l"
            if _RE_WEIGHT_IN_UNIT.search(product_unit):
                return "kg"

        # 2. Keyword matching on product name
        if not product_name:
            return "kg"

        name_lower = product_name.lower()
        weight_hits = sum(1 for kw in _WEIGHT_KEYWORDS if kw in name_lower)
        volume_hits = sum(1 for kw in _VOLUME_KEYWORDS if kw in name_lower)

        if volume_hits > weight_hits:
            return "l"
        # Default to kg (more common in Italian supermarkets)
        return "kg"

    @staticmethod
    def compute(
        offer_price: Decimal,
        quantity_str: Optional[str],
        product_name: Optional[str] = None,
        product_unit: Optional[str] = None,
    ) -> tuple[Optional[Decimal], Optional[str]]:
        """Attempt to compute the unit price.

        Returns ``(price_per_unit, unit_reference)`` on success, or
        ``(None, None)`` when the quantity cannot be parsed.

        ``unit_reference`` is one of ``"kg"``, ``"l"``, ``"pz"``.
        """
        if offer_price is None or offer_price <= 0:
            return None, None

        # Try parsing from quantity_str first, then product_name
        for text in [quantity_str, product_name, product_unit]:
            if not text:
                continue
            text = text.strip()
            result = UnitPriceCalculator._try_parse(offer_price, text)
            if result[0] is not None:
                return result

        return None, None

    @staticmethod
    def _try_parse(
        offer_price: Decimal, text: str
    ) -> tuple[Optional[Decimal], Optional[str]]:
        """Try all regex patterns against *text*."""

        # 1. Multi-pack: "6 x 1,5 L"
        m = _RE_MULTIPACK.search(text)
        if m:
            try:
                count = int(m.group(1))
                qty = _parse_decimal(m.group(2))
                unit_str = m.group(3).lower()
                total_qty, ref_unit = UnitPriceCalculator._normalise(
                    qty * count, unit_str
                )
                if total_qty and total_qty > 0:
                    ppu = (offer_price / total_qty).quantize(Decimal("0.01"))
                    return ppu, ref_unit
            except (InvalidOperation, ValueError, ZeroDivisionError):
                pass

        # 2. Simple quantity + unit: "500g", "1,5 L"
        m = _RE_QTY_UNIT.search(text)
        if m:
            try:
                qty = _parse_decimal(m.group(1))
                unit_str = m.group(2).lower()
                total_qty, ref_unit = UnitPriceCalculator._normalise(qty, unit_str)
                if total_qty and total_qty > 0:
                    ppu = (offer_price / total_qty).quantize(Decimal("0.01"))
                    return ppu, ref_unit
            except (InvalidOperation, ValueError, ZeroDivisionError):
                pass

        # 3. Count words: "4 pezzi", "6 rotoli"
        m = _RE_COUNT.search(text)
        if m:
            try:
                count = int(m.group(1))
                if count > 0:
                    ppu = (offer_price / count).quantize(Decimal("0.01"))
                    return ppu, "pz"
            except (InvalidOperation, ValueError, ZeroDivisionError):
                pass

        return None, None

    @staticmethod
    def _normalise(qty: Decimal, unit_str: str) -> tuple[Optional[Decimal], Optional[str]]:
        """Convert quantity to the reference unit (kg or l)."""
        if unit_str in _WEIGHT_UNITS:
            factor = _WEIGHT_UNITS[unit_str]
            return qty * factor, "kg"
        if unit_str in _VOLUME_UNITS:
            factor = _VOLUME_UNITS[unit_str]
            return qty * factor, "l"
        return None, None
