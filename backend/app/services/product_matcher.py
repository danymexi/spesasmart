"""Product deduplication service.

Uses fuzzy matching (rapidfuzz) to identify and merge duplicate product
entries coming from different flyers, chains and OCR extractions.
"""

import logging
import re
import uuid
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
    def fuzzy_match(name1: str, name2: str) -> float:
        """Return a similarity score (0-100) using token-sort ratio.

        ``token_sort_ratio`` is more robust than plain ``ratio`` because it
        handles word-order differences that are common in OCR output.
        """
        n1 = ProductMatcher.normalize_text(name1)
        n2 = ProductMatcher.normalize_text(name2)
        if not n1 or not n2:
            return 0.0
        return fuzz.token_sort_ratio(n1, n2)

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

        Returns ``None`` when no product scores above ``MATCH_THRESHOLD``.
        """
        close_session = False
        if session is None:
            session = async_session()
            close_session = True

        try:
            canonical_brand = self.normalize_brand(brand)

            # Pre-filter: use significant tokens from the name to narrow
            # candidates via SQL ILIKE instead of loading every product.
            tokens = self.normalize_text(name).split()
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
                score = self.fuzzy_match(name, product.name)

                # Give a bonus when brands match exactly
                if canonical_brand and product.brand == canonical_brand:
                    score = min(score + 5, 100.0)

                if score > best_score:
                    best_score = score
                    best_product = product

            if best_score >= MATCH_THRESHOLD and best_product is not None:
                logger.info(
                    "Matched '%s' -> '%s' (score=%.1f)",
                    name,
                    best_product.name,
                    best_score,
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
                    return existing

            # --- 2. Fuzzy name match ---
            matched = await self.find_matching_product(
                name, brand, session=session
            )
            if matched is not None:
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
