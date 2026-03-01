"""Product deduplication service.

Uses fuzzy matching (rapidfuzz) to identify and merge duplicate product
entries coming from different flyers, chains and OCR extractions.
"""

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from rapidfuzz import fuzz
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import Product

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MATCH_THRESHOLD = 85  # similarity >= 85 % ⇒ treat as the same product
BRAND_MATCH_THRESHOLD = 80  # lower threshold when brands match exactly

# Italian food-variant words that DISTINGUISH products (not stopwords).
# If these appear only in one name, the products are likely different.
_VARIANT_WORDS: set[str] = {
    # Flavors / ingredients
    "basilico", "limone", "arancia", "fragola", "vaniglia", "cioccolato",
    "pistacchio", "nocciola", "caffè", "caffe", "menta", "pesca",
    "frutti", "bosco", "miele", "zenzero", "aglio", "peperoncino",
    "pomodoro", "funghi", "tartufo", "olive", "capperi", "tonno",
    "prosciutto", "salmone", "formaggio", "mozzarella",
    # Variants
    "bio", "integrale", "integrali", "classico", "classica",
    "originale", "light", "zero", "senza", "glutine",
    "decaffeinato", "decaf",
    # Sizes / quantities that matter
    "mini", "maxi", "grande", "piccolo", "famiglia",
}

# Italian stopwords commonly seen in product names on flyers
_STOPWORDS: set[str] = {
    "di", "del", "della", "delle", "dei", "degli", "da", "al", "alla",
    "alle", "il", "lo", "la", "le", "gli", "i", "un", "una", "uno",
    "con", "per", "in", "su", "tra", "fra", "e", "o", "ed",
}

# Unit normalisation map  (raw form -> canonical)
_UNIT_MAP: dict[str, str] = {
    "grammi": "g",
    "gr": "g",
    "gr.": "g",
    "kg": "kg",
    "kilo": "kg",
    "kilogrammi": "kg",
    "litri": "l",
    "litro": "l",
    "lt": "l",
    "lt.": "l",
    "ml": "ml",
    "millilitri": "ml",
    "cl": "cl",
    "centilitri": "cl",
    "pezzi": "pz",
    "pz": "pz",
    "pz.": "pz",
    "conf": "conf",
    "conf.": "conf",
    "confezione": "conf",
    "confezioni": "conf",
    "rotoli": "rotoli",
    "rotolo": "rotoli",
    "capsule": "caps",
    "caps": "caps",
}

# Common Italian supermarket brand aliases (lowercase variant -> canonical)
BRAND_ALIASES: dict[str, str] = {
    "mulino bianco": "Mulino Bianco",
    "mulinobianco": "Mulino Bianco",
    "barilla": "Barilla",
    "de cecco": "De Cecco",
    "divella": "Divella",
    "voiello": "Voiello",
    "rummo": "Rummo",
    "garofalo": "Garofalo",
    "rio mare": "Rio Mare",
    "rio-mare": "Rio Mare",
    "star": "Star",
    "knorr": "Knorr",
    "findus": "Findus",
    "buitoni": "Buitoni",
    "galbani": "Galbani",
    "parmalat": "Parmalat",
    "granarolo": "Granarolo",
    "muller": "Muller",
    "müller": "Muller",
    "danone": "Danone",
    "ferrero": "Ferrero",
    "nutella": "Ferrero",
    "lavazza": "Lavazza",
    "illy": "Illy",
    "kimbo": "Kimbo",
    "scottex": "Scottex",
    "regina": "Regina",
    "dash": "Dash",
    "dixan": "Dixan",
    "ace": "ACE",
    "cocacola": "Coca-Cola",
    "coca cola": "Coca-Cola",
    "coca-cola": "Coca-Cola",
    "pepsi": "Pepsi",
    "san benedetto": "San Benedetto",
    "san pellegrino": "San Pellegrino",
    "sanpellegrino": "San Pellegrino",
    "levissima": "Levissima",
    "esselunga": "Esselunga",
}


class ProductMatcher:
    """Finds existing products by fuzzy-matching or creates new ones."""

    # ------------------------------------------------------------------
    # Text helpers
    # ------------------------------------------------------------------

    @staticmethod
    def normalize_text(text: str) -> str:
        """Lowercase, strip accents, remove stopwords and normalise units."""
        if not text:
            return ""

        text = text.lower().strip()

        # Collapse multiple spaces / tabs
        text = re.sub(r"\s+", " ", text)

        # Normalise units that appear as standalone tokens
        tokens: list[str] = []
        for token in text.split():
            canonical = _UNIT_MAP.get(token)
            if canonical:
                tokens.append(canonical)
            elif token not in _STOPWORDS:
                tokens.append(token)

        return " ".join(tokens)

    @staticmethod
    def _strip_brand(name: str, brand: str | None) -> str:
        """Remove brand name from the beginning of a product name.

        Esselunga embeds brand in the name (e.g. "Granarolo Latte Intero UHT
        1 L") while Iperal keeps brand separate.  Stripping it before matching
        greatly improves cross-source dedup.
        """
        if not brand or not name:
            return name
        name_lower = name.lower()
        brand_lower = brand.lower().strip()

        # Build brand variants: original + hyphen/space swapped
        brand_variants = {brand_lower}
        brand_variants.add(brand_lower.replace("-", " "))
        brand_variants.add(brand_lower.replace(" ", "-"))

        # Strip brand at beginning of name (possibly followed by comma/dash)
        for bv in brand_variants:
            for sep in ["", ",", " -", " –"]:
                prefix = bv + sep
                if name_lower.startswith(prefix):
                    cleaned = name[len(prefix):].lstrip(" ,.-–")
                    if cleaned:
                        return cleaned
        return name

    @staticmethod
    def _strip_units(text: str) -> str:
        """Remove unit/weight/volume patterns from text for cleaner matching.

        Strips patterns like '500g', '1 L', '1000 ml', '1,5 kg', '6 x 1,5 l'.
        """
        # Remove multi-pack patterns: "6 x 1,5 l", "4x500 ml"
        text = re.sub(
            r"\b\d+\s*x\s*\d+(?:[.,]\d+)?\s*(?:g|kg|ml|cl|l)\b",
            "", text, flags=re.IGNORECASE,
        )
        # Remove simple unit patterns: "500g", "1 L", "1000 ml", "1,5 kg"
        text = re.sub(
            r"\b\d+(?:[.,]\d+)?\s*(?:g|kg|ml|cl|l|pz|pezzi|conf)\b",
            "", text, flags=re.IGNORECASE,
        )
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def extract_brand_from_name(raw_name: str) -> tuple[str | None, str]:
        """Split ``"Brand - Product Name"`` into (brand, product_name).

        Tiendeo and other sources format names as ``"Barilla - Penne Rigate 500g"``.
        Returns ``(None, raw_name)`` when no separator is found.
        """
        if not raw_name:
            return None, raw_name

        # Pattern: "Brand - Product" (with surrounding spaces around the dash)
        if " - " in raw_name:
            parts = raw_name.split(" - ", 1)
            brand_candidate = parts[0].strip()
            product_name = parts[1].strip()
            # Only treat as brand if the left part is short-ish (≤ 4 words)
            if brand_candidate and len(brand_candidate.split()) <= 4 and product_name:
                return brand_candidate, product_name

        return None, raw_name.strip()

    @staticmethod
    def normalize_brand(brand: str | None) -> str | None:
        """Return canonical brand name or the original (title-cased)."""
        if not brand:
            return None
        key = brand.lower().strip()
        return BRAND_ALIASES.get(key, brand.strip().title())

    # ------------------------------------------------------------------
    # Fuzzy matching
    # ------------------------------------------------------------------

    @staticmethod
    def fuzzy_match(
        name1: str,
        name2: str,
        brand1: str | None = None,
        brand2: str | None = None,
    ) -> float:
        """Return a similarity score (0-100) for two product names.

        When both brands are known and match, strip the brand from names and
        use ``token_set_ratio`` (robust to one name being a subset of the
        other, e.g. "Latte Intero" ⊂ "Latte Intero UHT a Lunga Conservazione").

        Otherwise fall back to ``token_sort_ratio`` which handles word-order
        differences common in OCR output.
        """
        # Clean names: strip brand and unit patterns
        c1 = ProductMatcher._strip_units(ProductMatcher._strip_brand(name1, brand1))
        c2 = ProductMatcher._strip_units(ProductMatcher._strip_brand(name2, brand2))

        n1 = ProductMatcher.normalize_text(c1)
        n2 = ProductMatcher.normalize_text(c2)
        if not n1 or not n2:
            return 0.0

        cb1 = ProductMatcher.normalize_brand(brand1) if brand1 else None
        cb2 = ProductMatcher.normalize_brand(brand2) if brand2 else None
        brands_match = cb1 and cb2 and cb1 == cb2
        brands_conflict = cb1 and cb2 and cb1 != cb2

        sort_score = fuzz.token_sort_ratio(n1, n2)

        # When brands are explicitly different, cap score to prevent false
        # merges of generic names (e.g. "Acqua Naturale" from two brands)
        if brands_conflict:
            return min(sort_score, 70.0)

        if brands_match:
            set_score = fuzz.token_set_ratio(n1, n2)

            t1 = set(n1.split())
            t2 = set(n2.split())

            # Guard against overly-generic short names (< 2 significant tokens)
            shorter = n1 if len(n1) < len(n2) else n2
            sig_tokens = [t for t in shorter.split() if len(t) > 2]
            if len(sig_tokens) < 2:
                # Too short to trust token_set_ratio alone — dampen it
                set_score = min(set_score, sort_score + 15)

            # Guard against generic overlap: if the shorter name's
            # product-identifying tokens (alphabetic, len>3) have low
            # overlap with the other name, token_set_ratio is misleading.
            # e.g. "latte 100% italiano" vs "olio extra vergine oliva 100%
            # italiano" share generic tokens but are different products.
            shorter_tokens = t1 if len(n1) < len(n2) else t2
            longer_tokens = t2 if len(n1) < len(n2) else t1
            product_tokens = [
                t for t in shorter_tokens if len(t) > 3 and t.isalpha()
            ]
            if product_tokens:
                overlap = sum(1 for t in product_tokens if t in longer_tokens)
                overlap_ratio = overlap / len(product_tokens)
                if overlap_ratio <= 0.5:
                    # Half or fewer product-identifying tokens match —
                    # these are different products sharing generic words
                    set_score = min(set_score, sort_score + 10)

            # Penalize when one name has variant-distinguishing words
            # that the other doesn't (e.g. "basilico", "integrale", "bio").
            # Use stems (first 6 chars) so "integrale"/"integrali" are
            # treated as the same variant, not different ones.
            diff1 = t1 - t2  # tokens only in name1
            diff2 = t2 - t1  # tokens only in name2
            var1_stems = {w[:6] for w in diff1 if w in _VARIANT_WORDS}
            var2_stems = {w[:6] for w in diff2 if w in _VARIANT_WORDS}
            # Only penalize when a variant stem appears in ONE side only
            unmatched_variants = var1_stems.symmetric_difference(var2_stems)
            if unmatched_variants:
                penalty = 25.0 * len(unmatched_variants)
                return max(sort_score - penalty, set_score - penalty, 0.0)

            return max(sort_score, set_score)

        return sort_score

    # ------------------------------------------------------------------
    # Database look-ups
    # ------------------------------------------------------------------

    async def find_matching_product(
        self,
        name: str,
        brand: str | None = None,
        *,
        session: AsyncSession | None = None,
    ) -> Optional[Product]:
        """Search existing products and return the best fuzzy match.

        If a *brand* is supplied the search is restricted to products that
        share the same canonical brand first; if nothing is found it falls
        back to a brand-agnostic search.

        Returns ``None`` when no product scores above the match threshold.
        """
        close_session = False
        if session is None:
            session = async_session()
            close_session = True

        try:
            canonical_brand = self.normalize_brand(brand)

            # Pre-filter: use significant tokens from the name (after
            # stripping brand and units) to narrow candidates via SQL ILIKE.
            cleaned = self._strip_units(self._strip_brand(name, brand))
            tokens = self.normalize_text(cleaned).split()
            significant = [t for t in tokens if len(t) > 3][:3]

            # Fetch candidates – restrict to same brand when available
            if canonical_brand:
                stmt = select(Product).where(Product.brand == canonical_brand)
                if significant:
                    stmt = stmt.where(
                        or_(*[Product.name.ilike(f"%{tok}%") for tok in significant])
                    )
                result = await session.execute(stmt)
                candidates: list[Product] = list(result.scalars().all())

                # If no candidates with that brand, widen to token-only search
                if not candidates and significant:
                    stmt = select(Product).where(
                        or_(*[Product.name.ilike(f"%{tok}%") for tok in significant])
                    )
                    result = await session.execute(stmt)
                    candidates = list(result.scalars().all())
            else:
                if significant:
                    stmt = select(Product).where(
                        or_(*[Product.name.ilike(f"%{tok}%") for tok in significant])
                    )
                else:
                    stmt = select(Product)
                result = await session.execute(stmt)
                candidates = list(result.scalars().all())

            if not candidates:
                return None

            best_score: float = 0.0
            best_product: Product | None = None

            for product in candidates:
                score = self.fuzzy_match(
                    name, product.name,
                    brand1=brand, brand2=product.brand,
                )

                # Give a bonus when brands match exactly
                if canonical_brand and product.brand == canonical_brand:
                    score = min(score + 5, 100.0)

                if score > best_score:
                    best_score = score
                    best_product = product

            # Use a lower threshold when brands match (the brand-aware
            # token_set_ratio already ensures quality)
            threshold = MATCH_THRESHOLD
            if (
                canonical_brand
                and best_product is not None
                and best_product.brand == canonical_brand
            ):
                threshold = BRAND_MATCH_THRESHOLD

            if best_score >= threshold and best_product is not None:
                logger.info(
                    "Matched '%s' -> '%s' (score=%.1f, threshold=%d)",
                    name,
                    best_product.name,
                    best_score,
                    threshold,
                )
                return best_product

            logger.debug(
                "No match for '%s' (best score=%.1f)", name, best_score
            )
            return None
        finally:
            if close_session:
                await session.close()

    # ------------------------------------------------------------------
    # Product enrichment on re-match
    # ------------------------------------------------------------------

    @staticmethod
    def _enrich_product(product: Product, raw_data: dict, now) -> None:
        """Fill in missing fields on a matched product from new raw data.

        Updates ``last_seen_at`` and fills blanks for category, subcategory,
        image_url, and unit — but never overwrites existing good data.
        """
        product.last_seen_at = now

        # Fill category if currently missing or generic
        new_cat = raw_data.get("category")
        if new_cat and (not product.category or product.category == "Supermercato"):
            product.category = new_cat

        new_sub = raw_data.get("subcategory")
        if new_sub and (not product.subcategory or product.subcategory == "Supermercato"):
            product.subcategory = new_sub

        # Fill image if missing
        new_img = raw_data.get("image_url")
        if new_img and not product.image_url:
            product.image_url = new_img

        # Fill unit if missing
        new_unit = raw_data.get("unit")
        if new_unit and not product.unit:
            product.unit = new_unit

    # ------------------------------------------------------------------
    # Create-or-match entry point
    # ------------------------------------------------------------------

    async def create_or_match_product(
        self,
        raw_data: dict,
        *,
        session: AsyncSession | None = None,
    ) -> Product:
        """Return an existing :class:`Product` or create a new one.

        ``raw_data`` is expected to carry at least a ``name`` key.  Optional
        keys: ``brand``, ``category``, ``subcategory``, ``unit``, ``barcode``,
        ``image_url``.
        """
        name: str = raw_data.get("name", "").strip()
        brand: str | None = raw_data.get("brand")

        if not name:
            raise ValueError("Product name is required in raw_data")

        close_session = False
        if session is None:
            session = async_session()
            close_session = True

        try:
            now = datetime.now(timezone.utc)
            source = raw_data.get("source")

            # --- 1. Exact barcode look-up (fastest) ---
            barcode = raw_data.get("barcode")
            if barcode:
                stmt = select(Product).where(Product.barcode == barcode)
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()
                if existing is not None:
                    logger.info(
                        "Barcode match '%s' -> product %s", barcode, existing.id
                    )
                    self._enrich_product(existing, raw_data, now)
                    await session.commit()
                    return existing

            # --- 2. Fuzzy name match ---
            matched = await self.find_matching_product(
                name, brand, session=session
            )
            if matched is not None:
                self._enrich_product(matched, raw_data, now)
                await session.commit()
                return matched

            # --- 3. Create new product ---
            canonical_brand = self.normalize_brand(brand)
            product = Product(
                id=uuid.uuid4(),
                name=name.strip(),
                brand=canonical_brand,
                category=raw_data.get("category"),
                subcategory=raw_data.get("subcategory"),
                unit=raw_data.get("unit"),
                barcode=barcode,
                image_url=raw_data.get("image_url"),
                source=source,
                last_seen_at=now,
            )
            session.add(product)
            await session.commit()
            await session.refresh(product)

            logger.info("Created new product %s – '%s'", product.id, product.name)
            return product
        except Exception:
            await session.rollback()
            raise
        finally:
            if close_session:
                await session.close()
