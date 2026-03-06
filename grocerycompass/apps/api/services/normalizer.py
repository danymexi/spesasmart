import re

from rapidfuzz import fuzz

UNIT_MAP = {
    'ml': 'ml', 'millilitri': 'ml', 'cl': 'ml',
    'l': 'l', 'lt': 'l', 'litri': 'l', 'litro': 'l',
    'g': 'g', 'gr': 'g', 'grammi': 'g', 'grammo': 'g',
    'kg': 'kg', 'kilo': 'kg', 'chilogrammo': 'kg',
    'pz': 'pz', 'pezzi': 'pz', 'pezzo': 'pz', 'unit': 'pz',
    'porzioni': 'pz', 'conf': 'pz', 'confezione': 'pz',
}

STORE_PREFIXES = [
    'esselunga', 'fior fiore', 'conad', 'verso natura',
    'carrefour', 'terre d\'italia', 'iperal', 'coop',
    'bene si', 'vivi verde', 'filiera qualita',
]


def parse_quantity(raw: str) -> dict:
    """
    Parse quantity strings like "1,5 L", "500g", "6x80g", "3 pz"
    Returns {"value": float, "unit": str, "pieces": int, "raw": str}
    """
    raw_clean = raw.lower().replace(',', '.').strip()

    # Multi-pack: "6x80g"
    multi = re.match(r'(\d+)\s*[xX×]\s*(\d+\.?\d*)\s*(\w+)', raw_clean)
    if multi:
        pieces = int(multi.group(1))
        val = float(multi.group(2))
        unit = UNIT_MAP.get(multi.group(3), multi.group(3))
        return {"value": pieces * val, "unit": unit, "pieces": pieces, "raw": raw}

    # Standard case
    match = re.match(r'(\d+\.?\d*)\s*(\w+)', raw_clean)
    if match:
        val = float(match.group(1))
        unit_raw = match.group(2)
        unit = UNIT_MAP.get(unit_raw, unit_raw)

        # Conversions
        if unit == 'cl':
            val *= 10
            unit = 'ml'
        if unit == 'l':
            val *= 1000
            unit = 'ml'

        return {"value": val, "unit": unit, "pieces": 1, "raw": raw}

    return {"value": None, "unit": None, "pieces": 1, "raw": raw}


def normalize_product_name(raw: str) -> str:
    """Normalize product name for matching."""
    name = raw.lower().strip()
    if not name:
        return ""

    # Remove store prefixes
    for prefix in STORE_PREFIXES:
        if name.startswith(prefix):
            name = name[len(prefix):].strip()

    # Remove quantities from name
    name = re.sub(r'\b\d+[,.]?\d*\s*(kg|g|gr|l|lt|ml|cl|pz|conf)\b', '', name)

    # Standardize whitespace
    name = ' '.join(name.split())

    # Remove quotes
    name = re.sub(r'["""\'']', '', name)

    return name.strip()


def compute_price_per_unit(price: float, qty: dict) -> tuple[float | None, str | None]:
    """
    Returns (price_per_unit, label) e.g. (1.20, "€/kg")
    """
    if not qty.get('value') or not qty.get('unit'):
        return None, None

    val = qty['value']
    unit = qty['unit']

    if unit == 'ml':
        price_per_l = price / (val / 1000)
        return round(price_per_l, 4), '€/l'
    elif unit == 'g':
        price_per_kg = price / (val / 1000)
        return round(price_per_kg, 4), '€/kg'
    elif unit == 'pz':
        return round(price / val, 4), '€/pz'

    return None, None


def match_products(
    name_a: str,
    brand_a: str | None,
    qty_a: dict,
    name_b: str,
    brand_b: str | None,
    qty_b: dict,
) -> float:
    """
    Compute match score between two products (0.0 - 1.0).
    """
    norm_a = normalize_product_name(name_a)
    norm_b = normalize_product_name(name_b)

    name_score = fuzz.token_sort_ratio(norm_a, norm_b) / 100.0

    # Brand similarity
    if brand_a and brand_b:
        brand_score = fuzz.ratio(brand_a.lower(), brand_b.lower()) / 100.0
    elif not brand_a and not brand_b:
        brand_score = 1.0
    else:
        brand_score = 0.0

    # Quantity similarity
    if qty_a.get('value') and qty_b.get('value') and qty_a.get('unit') == qty_b.get('unit'):
        qty_diff = abs(qty_a['value'] - qty_b['value']) / max(qty_a['value'], qty_b['value'])
        qty_score = max(0, 1.0 - qty_diff)
    elif not qty_a.get('value') and not qty_b.get('value'):
        qty_score = 1.0
    else:
        qty_score = 0.0

    # Weights depend on brand availability
    if brand_a and brand_b:
        score = 0.4 * brand_score + 0.4 * name_score + 0.2 * qty_score
    else:
        score = 0.6 * name_score + 0.4 * qty_score

    return round(score, 3)
