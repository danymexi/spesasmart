"""API routes for products."""

import logging
import re
import uuid
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from difflib import SequenceMatcher

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from sqlalchemy import or_

from app.database import get_db
from app.models import Category, Chain, Offer, Product

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/products", tags=["products"])

# Italian grocery synonym map for common misspellings and aliases
_ITALIAN_SYNONYMS: dict[str, str] = {
    "parmigano": "parmigiano",
    "parmigiana": "parmigiano",
    "parmesano": "parmigiano",
    "gorgonzola": "gorgonzola",
    "mozzarela": "mozzarella",
    "mozarella": "mozzarella",
    "prosciuto": "prosciutto",
    "yoghurt": "yogurt",
    "jogurt": "yogurt",
    "yougurt": "yogurt",
    "cioccolata": "cioccolato",
    "ciocolato": "cioccolato",
    "olio evo": "olio extravergine",
    "olio ev": "olio extravergine",
    "pomodorini": "pomodori",
    "insalatina": "insalata",
    "riso": "riso",
    "brocoli": "broccoli",
    "farina oo": "farina 00",
    "acqua nat": "acqua naturale",
    "acqua friz": "acqua frizzante",
    "tonno olio": "tonno olio",
    "prosciutto cotto": "prosciutto cotto",
    "prosciutto crudo": "prosciutto crudo",
    # Common typos and brand variants
    "nutela": "nutella",
    "coca cola": "coca-cola",
    "cocacola": "coca-cola",
    "spek": "speck",
    "mortadela": "mortadella",
    "Philadelphia": "philadelphia",
    "stracchino": "stracchino",
    "mascrapone": "mascarpone",
    "proscutto": "prosciutto",
    "salsicia": "salsiccia",
    "bagnodoccia": "bagnoschiuma",
    "detersivio": "detersivo",
    "bisccotti": "biscotti",
    "crackers": "cracker",
}


def _expand_synonyms(q: str) -> str:
    """Expand known Italian grocery synonyms/misspellings in query."""
    q_lower = q.lower().strip()
    for typo, correct in _ITALIAN_SYNONYMS.items():
        if typo in q_lower:
            q_lower = q_lower.replace(typo, correct)
    return q_lower


def _build_search_filter(q: str):
    """Build a search filter that matches each word against name OR brand.

    "latte valtellina" → name+brand must contain both "latte" AND "valtellina"
    (each word can be in either field).
    """
    expanded = _expand_synonyms(q)
    words = expanded.strip().split()
    conditions = []
    for word in words:
        pattern = f"%{word}%"
        conditions.append(or_(Product.name.ilike(pattern), Product.brand.ilike(pattern)))
    return conditions


async def _fuzzy_search_products(
    q: str,
    db: AsyncSession,
    limit: int = 20,
    category: str | None = None,
    min_similarity: float = 0.2,
) -> list["Product"]:
    """Fallback fuzzy search using pg_trgm similarity when ILIKE finds nothing."""
    expanded = _expand_synonyms(q)

    # Use similarity() function from pg_trgm
    similarity_expr = func.similarity(Product.name, expanded)
    brand_similarity = func.similarity(func.coalesce(Product.brand, ""), expanded)
    combined_score = func.greatest(similarity_expr, brand_similarity)

    query = (
        select(Product, combined_score.label("score"))
        .where(combined_score >= min_similarity)
    )
    if category:
        query = query.where(Product.category.ilike(f"%{category}%"))
    query = query.order_by(combined_score.desc()).limit(limit)

    result = await db.execute(query)
    return [row[0] for row in result.all()]


class ProductResponse(BaseModel):
    id: uuid.UUID
    name: str
    brand: str | None
    category: str | None
    subcategory: str | None
    unit: str | None
    image_url: str | None

    model_config = {"from_attributes": True}


class CatalogProductResponse(BaseModel):
    id: uuid.UUID
    name: str
    brand: str | None
    category: str | None
    image_url: str | None
    has_active_offer: bool
    best_offer_price: Decimal | None
    best_chain_name: str | None
    best_price_per_unit: Decimal | None = None
    unit_reference: str | None = None
    unit: str | None = None
    price_indicator: str | None = None  # "top" | "neutro" | "flop"


class CategoryResponse(BaseModel):
    name: str
    count: int


class CategoryChild(BaseModel):
    id: str
    name: str
    slug: str
    icon: str | None = None


class CategoryTree(BaseModel):
    id: str
    name: str
    slug: str
    icon: str | None = None
    count: int = 0
    children: list[CategoryChild] = []


class PriceHistoryPoint(BaseModel):
    date: date
    price: Decimal
    chain_name: str
    chain_slug: str | None = None
    discount_type: str | None
    price_per_unit: Decimal | None = None
    unit_reference: str | None = None


class PriceHistoryResponse(BaseModel):
    product: ProductResponse
    history: list[PriceHistoryPoint]


class BestPriceResponse(BaseModel):
    product: ProductResponse
    best_price: Decimal
    chain_name: str
    valid_until: date | None
    original_price: Decimal | None
    discount_pct: Decimal | None
    price_per_unit: Decimal | None = None
    unit_reference: str | None = None
    price_indicator: str | None = None


class ProductSearchResult(BaseModel):
    product: ProductResponse
    best_current_price: Decimal | None = None
    chain_name: str | None = None
    offers_count: int = 0


class CatalogPreloadItem(BaseModel):
    id: uuid.UUID
    name: str
    brand: str | None
    category: str | None
    image_url: str | None
    best_price: Decimal | None
    best_chain: str | None
    best_chain_slug: str | None


@router.get("/catalog/preload", response_model=list[CatalogPreloadItem])
async def get_catalog_preload(
    db: AsyncSession = Depends(get_db),
):
    """Return all products with an active offer for frontend pre-caching.

    Single non-paginated payload (typically 500-2000 items) intended to be
    fetched once in background at app startup.
    """
    today = date.today()

    best_offer_sq = (
        select(
            Offer.product_id,
            func.min(Offer.offer_price).label("best_price"),
        )
        .where(Offer.valid_from <= today, Offer.valid_to >= today)
        .group_by(Offer.product_id)
        .subquery()
    )

    query = (
        select(Product, best_offer_sq.c.best_price)
        .join(best_offer_sq, Product.id == best_offer_sq.c.product_id)
        .order_by(Product.name)
    )

    result = await db.execute(query)
    rows = result.all()

    if not rows:
        return []

    product_ids = [r.Product.id for r in rows]
    chain_query = (
        select(Offer.product_id, Chain.name, Chain.slug)
        .join(Chain, Offer.chain_id == Chain.id)
        .where(
            Offer.product_id.in_(product_ids),
            Offer.valid_from <= today,
            Offer.valid_to >= today,
        )
        .order_by(Offer.offer_price)
    )
    chain_result = await db.execute(chain_query)
    chain_map: dict[uuid.UUID, tuple[str, str]] = {}
    for pid, cname, cslug in chain_result.all():
        if pid not in chain_map:
            chain_map[pid] = (cname, cslug)

    return [
        CatalogPreloadItem(
            id=row.Product.id,
            name=row.Product.name,
            brand=row.Product.brand,
            category=row.Product.category,
            image_url=row.Product.image_url,
            best_price=row.best_price,
            best_chain=chain_map.get(row.Product.id, (None, None))[0],
            best_chain_slug=chain_map.get(row.Product.id, (None, None))[1],
        )
        for row in rows
    ]


@router.get("/catalog", response_model=list[CatalogProductResponse])
async def get_catalog_products(
    category: str | None = Query(None),
    brand: str | None = Query(None),
    q: str | None = Query(None),
    sort: str | None = Query(None, enum=["name", "price", "price_per_unit"]),
    chain: str | None = Query(None, description="Comma-separated chain slugs"),
    limit: int = Query(50, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Browse the full product catalog with optional filters."""
    today = date.today()

    # Build subquery for best active offer per product
    best_offer_where = [Offer.valid_from <= today, Offer.valid_to >= today]
    if chain:
        chain_slugs = [s.strip() for s in chain.split(",")]
        best_offer_where.append(
            Offer.chain_id.in_(
                select(Chain.id).where(Chain.slug.in_(chain_slugs))
            )
        )

    best_offer_sq = (
        select(
            Offer.product_id,
            func.min(Offer.offer_price).label("best_price"),
            func.min(Offer.price_per_unit).label("best_ppu"),
        )
        .where(*best_offer_where)
        .group_by(Offer.product_id)
        .subquery()
    )

    # Subquery for unit_reference of the cheapest offer per product
    unit_ref_sq = (
        select(
            Offer.product_id,
            Offer.unit_reference,
        )
        .where(
            Offer.valid_from <= today,
            Offer.valid_to >= today,
            Offer.price_per_unit.isnot(None),
        )
        .distinct(Offer.product_id)
        .order_by(Offer.product_id, Offer.price_per_unit)
        .subquery()
    )

    # Subquery for historical average price per product
    avg_price_sq = (
        select(
            Offer.product_id,
            func.avg(Offer.offer_price).label("avg_price"),
        )
        .group_by(Offer.product_id)
        .subquery()
    )

    # Main query
    query = (
        select(
            Product,
            best_offer_sq.c.best_price,
            best_offer_sq.c.best_ppu,
            unit_ref_sq.c.unit_reference,
            avg_price_sq.c.avg_price,
        )
        .outerjoin(best_offer_sq, Product.id == best_offer_sq.c.product_id)
        .outerjoin(unit_ref_sq, Product.id == unit_ref_sq.c.product_id)
        .outerjoin(avg_price_sq, Product.id == avg_price_sq.c.product_id)
    )

    if category:
        variants = _reverse_category_lookup(category)
        if len(variants) > 1:
            query = query.where(or_(*[Product.category.ilike(v) for v in variants]))
        else:
            query = query.where(Product.category.ilike(category))
    if brand:
        query = query.where(Product.brand.ilike(f"%{brand}%"))
    if q:
        for cond in _build_search_filter(q):
            query = query.where(cond)

    # When filtering by chain, only show products with an active offer in that chain
    if chain:
        query = query.where(best_offer_sq.c.best_price.isnot(None))

    # Sorting
    if sort == "price":
        query = query.order_by(best_offer_sq.c.best_price.asc().nulls_last())
    elif sort == "price_per_unit":
        query = query.order_by(best_offer_sq.c.best_ppu.asc().nulls_last())
    else:
        query = query.order_by(Product.name)

    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    rows = result.all()

    # For rows that have an active offer, find the chain name
    products_with_offers = [r.Product.id for r in rows if r.best_price is not None]
    chain_map: dict[uuid.UUID, str] = {}
    if products_with_offers:
        chain_query = (
            select(Offer.product_id, Chain.name)
            .join(Chain, Offer.chain_id == Chain.id)
            .where(
                Offer.product_id.in_(products_with_offers),
                Offer.valid_from <= today,
                Offer.valid_to >= today,
            )
            .order_by(Offer.offer_price)
        )
        chain_result = await db.execute(chain_query)
        for pid, cname in chain_result.all():
            if pid not in chain_map:
                chain_map[pid] = cname

    # Compute price indicators using PriceAnalyzer batch method
    from app.services.price_analyzer import PriceAnalyzer

    product_ids_with_offers = [r.Product.id for r in rows if r.best_price is not None]
    analyzer = PriceAnalyzer()
    indicators = await analyzer.compute_indicators_batch(
        product_ids_with_offers, session=db
    ) if product_ids_with_offers else {}

    return [
        CatalogProductResponse(
            id=row.Product.id,
            name=row.Product.name,
            brand=row.Product.brand,
            category=row.Product.category,
            image_url=row.Product.image_url,
            has_active_offer=row.best_price is not None,
            best_offer_price=row.best_price,
            best_chain_name=chain_map.get(row.Product.id),
            best_price_per_unit=row.best_ppu,
            unit_reference=row.unit_reference,
            unit=row.Product.unit,
            price_indicator=indicators.get(row.Product.id),
        )
        for row in rows
    ]


def _normalize_product_name(name: str) -> str:
    """Normalize a product name for fuzzy grouping.

    Applies: private-label stripping, abbreviation expansion,
    Italian plural stemming, quantity removal.
    """
    from app.services.product_matcher import (
        ProductMatcher,
        _ABBREVIATION_MAP,
    )

    # Strip private-label prefixes first
    n = ProductMatcher._strip_private_label(name)
    n = n.lower().strip()
    # Expand multi-token abbreviations
    n = ProductMatcher._expand_abbreviations(n)
    # Remove common quantity/size suffixes and trailing numbers
    n = re.sub(r"\b\d+\s*(pz|pezzi|rotoli|x|ml|cl|l|g|kg|gr)\b", "", n)
    n = re.sub(r"\bx\s*\d+\b", "", n)
    # Remove "carta igienica", "carta cucina" etc. (generic product type)
    n = re.sub(r"\bcarta\s+(igienica|cucina|assorbente)\b", "", n)
    n = re.sub(r"\s+", " ", n).strip()
    # Expand single-token abbreviations and apply Italian stemming
    tokens = []
    for token in n.split():
        expanded = _ABBREVIATION_MAP.get(token)
        if expanded:
            token = expanded
        tokens.append(ProductMatcher._stem_italian(token))
    return " ".join(tokens)


def _names_match(norm_a: str, norm_b: str, threshold: float = 0.78) -> bool:
    """Check if two normalized names refer to the same product.

    Uses three strategies:
    1. Substring containment (shorter name inside longer, min 6 chars
       AND shorter must be at least 50% of longer's length)
    2. Shared-prefix match (first 2+ words in common)
    3. SequenceMatcher ratio above threshold
    """
    shorter, longer = sorted([norm_a, norm_b], key=len)

    # Strategy 1: substring containment with length guard
    # "rotoloni" in "rotoloni regina" → OK (8/17 = 47%, but same core)
    # "vaniglia" in "biscotti vaniglia cioccolato" → rejected (too short
    # relative to longer name and in the middle, not a prefix)
    if len(shorter) >= 6 and shorter in longer:
        # Only accept if shorter starts at position 0 (prefix) OR is
        # at least 40% of the longer name's length
        pos = longer.find(shorter)
        if pos == 0 or len(shorter) / len(longer) >= 0.4:
            return True

    # Strategy 2: shared significant words (first 2+ words match)
    words_a = norm_a.split()
    words_b = norm_b.split()
    if len(words_a) >= 2 and len(words_b) >= 2:
        common_prefix = 0
        for wa, wb in zip(words_a, words_b):
            if wa == wb:
                common_prefix += 1
            else:
                break
        if common_prefix >= 2:
            return True

    # Strategy 3: fuzzy ratio
    ratio = SequenceMatcher(None, norm_a, norm_b).ratio()
    return ratio >= threshold


def _is_valid_ean(code: str | None) -> bool:
    """Check if a string looks like a valid EAN-8 or EAN-13."""
    return bool(code and code.isdigit() and len(code) in (8, 13))


def _group_similar_products(products: list[Product]) -> list[list[Product]]:
    """Group products with similar names, barcode-first.

    Phase A: group products sharing the same valid EAN barcode (exact, fast).
    Phase B: fuzzy name matching for remaining products (existing logic).

    Brand check is soft BUT only for descriptive names (>=3 words).
    Short/generic names like "Vaniglia" ALWAYS require matching brand
    because they could refer to completely different products (biscuits,
    yogurt, protein drink, etc.).
    """
    groups: list[list[Product]] = []
    used: set[int] = set()
    normalized = [_normalize_product_name(p.name) for p in products]

    # --- Phase A: Group by barcode (exact, fast) ---
    barcode_map: dict[str, list[int]] = {}
    for i, p in enumerate(products):
        bc = p.barcode
        if _is_valid_ean(bc):
            barcode_map.setdefault(bc, []).append(i)

    for bc, indices in barcode_map.items():
        if len(indices) < 2:
            continue
        # Mark all but the first as "used" — they'll join the first's group below
        first = indices[0]
        for idx in indices[1:]:
            used.add(idx)

    # --- Phase B: Fuzzy name matching (with barcode awareness) ---
    for i, p in enumerate(products):
        if i in used:
            continue
        group = [p]
        used.add(i)
        brand_i = (p.brand or "").lower().strip()
        cat_i = (p.category or "").strip()
        bc_i = p.barcode if _is_valid_ean(p.barcode) else None

        for j in range(i + 1, len(products)):
            if j in used:
                continue
            q = products[j]
            bc_j = q.barcode if _is_valid_ean(q.barcode) else None

            # Barcode match — instant group (skip name check)
            if bc_i and bc_j and bc_i == bc_j:
                group.append(q)
                used.add(j)
                continue

            # Barcode conflict — never group
            if bc_i and bc_j and bc_i != bc_j:
                continue

            brand_j = (q.brand or "").lower().strip()
            cat_j = (q.category or "").strip()
            brands_differ = brand_i and brand_j and brand_i != brand_j

            # Category guard: never group products from different categories
            if (
                cat_i and cat_j
                and cat_i != cat_j
                and cat_i != "Supermercato"
                and cat_j != "Supermercato"
            ):
                continue

            if not _names_match(normalized[i], normalized[j]):
                continue

            if brands_differ:
                # Only allow cross-brand grouping when the name is
                # descriptive enough (>=3 words) to identify a specific
                # product.  "Vaniglia" (1 word) is too generic.
                shorter, longer = sorted(
                    [normalized[i], normalized[j]], key=len
                )
                word_count = len(shorter.split())
                if word_count < 3:
                    continue

                ratio = SequenceMatcher(
                    None, normalized[i], normalized[j]
                ).ratio()
                strong = (
                    ratio >= 0.85
                    or (len(shorter) >= 6 and shorter in longer)
                )
                if not strong:
                    continue

            group.append(q)
            used.add(j)
        groups.append(group)
    return groups


# Lightweight row type for pre-pagination grouping
_ProductTuple = tuple[uuid.UUID, str, str | None, str | None, str | None]  # id, name, brand, category, barcode


def _group_similar_product_ids(
    rows: list[_ProductTuple],
) -> list[list[uuid.UUID]]:
    """Same logic as _group_similar_products but on lightweight (id, name, brand, category, barcode) tuples.

    Returns groups of product IDs.
    """
    groups: list[list[uuid.UUID]] = []
    used: set[int] = set()
    normalized = [_normalize_product_name(r[1]) for r in rows]
    # Pre-compute first words for quick rejection
    first_words = [n.split()[0] if n else "" for n in normalized]

    # --- Phase A: Group by barcode (exact, fast) ---
    barcode_map: dict[str, list[int]] = {}
    for i, r in enumerate(rows):
        bc = r[4]
        if _is_valid_ean(bc):
            barcode_map.setdefault(bc, []).append(i)

    for bc, indices in barcode_map.items():
        if len(indices) < 2:
            continue
        first = indices[0]
        for idx in indices[1:]:
            used.add(idx)

    # --- Phase B: Fuzzy name matching (limited to nearby neighbours) ---
    # Products are sorted by name, so duplicates with similar names are adjacent.
    # Limit the inner loop to WINDOW neighbours to avoid O(n²) on large catalogs.
    WINDOW = 50
    for i, r in enumerate(rows):
        if i in used:
            continue
        group_ids = [r[0]]
        used.add(i)
        brand_i = (r[2] or "").lower().strip()
        cat_i = (r[3] or "").strip()
        bc_i = r[4] if _is_valid_ean(r[4]) else None

        for j in range(i + 1, min(i + 1 + WINDOW, len(rows))):
            if j in used:
                continue
            q = rows[j]
            bc_j = q[4] if _is_valid_ean(q[4]) else None

            # Barcode match — instant group
            if bc_i and bc_j and bc_i == bc_j:
                group_ids.append(q[0])
                used.add(j)
                continue

            # Barcode conflict — never group
            if bc_i and bc_j and bc_i != bc_j:
                continue

            brand_j = (q[2] or "").lower().strip()
            cat_j = (q[3] or "").strip()
            brands_differ = brand_i and brand_j and brand_i != brand_j

            # Category guard
            if (
                cat_i and cat_j
                and cat_i != cat_j
                and cat_i != "Supermercato"
                and cat_j != "Supermercato"
            ):
                continue

            # Quick first-word rejection (avoid expensive SequenceMatcher)
            # Cross-match first 2 words to handle "Barilla Spaghetti" vs "Spaghetti Barilla"
            if first_words[i] and first_words[j] and first_words[i][:4] != first_words[j][:4]:
                words_i = normalized[i].split()[:2]
                words_j = normalized[j].split()[:2]
                cross_match = any(
                    wi[:4] == wj[:4] for wi in words_i for wj in words_j
                )
                if not cross_match:
                    continue

            if not _names_match(normalized[i], normalized[j]):
                continue

            if brands_differ:
                shorter, longer = sorted(
                    [normalized[i], normalized[j]], key=len
                )
                word_count = len(shorter.split())
                if word_count < 3:
                    continue
                ratio = SequenceMatcher(
                    None, normalized[i], normalized[j]
                ).ratio()
                strong = (
                    ratio >= 0.85
                    or (len(shorter) >= 6 and shorter in longer)
                )
                if not strong:
                    continue

            group_ids.append(q[0])
            used.add(j)
        groups.append(group_ids)
    return groups


def _is_similar_product(
    prod_norm: str, prod_brand: str,
    candidate_norm: str, candidate_brand: str,
    prod_category: str = "", candidate_category: str = "",
) -> bool:
    """Check if a candidate product is similar enough to group with prod."""
    # Category guard
    if (
        prod_category and candidate_category
        and prod_category != candidate_category
        and prod_category != "Supermercato"
        and candidate_category != "Supermercato"
    ):
        return False
    if not _names_match(prod_norm, candidate_norm, threshold=0.80):
        return False
    shorter, longer = sorted([prod_norm, candidate_norm], key=len)
    if len(longer) > 0 and len(shorter) / len(longer) < 0.5:
        return False
    if prod_brand and candidate_brand and prod_brand != candidate_brand:
        if len(shorter.split()) < 3:
            return False
        ratio = SequenceMatcher(None, prod_norm, candidate_norm).ratio()
        if not (ratio >= 0.85 or (len(shorter) >= 6 and shorter in longer)):
            return False
    return True


async def _find_similar_ids(product: Product, db: AsyncSession) -> list:
    """Find product IDs similar to the given product (for cross-chain compare)."""
    from app.services.product_matcher import ProductMatcher

    product_ids = [product.id]

    # Extract significant keywords (stemmed, >=4 chars, not stopwords)
    _stopwords = {
        "alla", "allo", "alle", "della", "dello", "delle", "con", "per",
        "dei", "degli", "del", "una", "uno",
    }
    norm_name = _normalize_product_name(product.name)
    keywords = [
        w for w in norm_name.split()
        if len(w) >= 4 and w.lower() not in _stopwords
    ][:3]  # Use up to 3 keywords

    if not keywords:
        return product_ids

    # Search using OR across multiple keywords
    keyword_filters = [Product.name.ilike(f"%{kw}%") for kw in keywords]
    cands = await db.execute(
        select(Product).where(
            or_(*keyword_filters),
            Product.id != product.id,
        )
    )

    prod_norm = norm_name
    prod_brand = (product.brand or "").lower().strip()
    prod_category = (product.category or "").strip()
    for cp in cands.scalars().all():
        cp_norm = _normalize_product_name(cp.name)
        cp_brand = (cp.brand or "").lower().strip()
        cp_category = (cp.category or "").strip()
        if _is_similar_product(
            prod_norm, prod_brand, cp_norm, cp_brand,
            prod_category, cp_category,
        ):
            product_ids.append(cp.id)
    return product_ids


# ── Category normalisation for catalog-home ──────────────────────────────────

# Maps raw category names (lowercased) → canonical display name.
# Categories that map to the same canonical name are merged.
_CATEGORY_NORM: dict[str, str] = {
    "salumi e formaggi": "Salumi e Formaggi",
    "salumi e Formaggi": "Salumi e Formaggi",
    "igiene personale": "Igiene e Cura Persona",
    "igiene e cura persona": "Igiene e Cura Persona",
    "pulizia casa": "Pulizia Casa",
    "cura della casa": "Pulizia Casa",
    "frutta e verdura": "Frutta e Verdura",
    "benessere & intolleranze": "Benessere e Intolleranze",
    "dolci, colazione e merenda": "Dolci e Snack",
    "dolci e snack": "Dolci e Snack",
    "olio, condimenti e conserve": "Condimenti e Conserve",
    "condimenti e conserve": "Condimenti e Conserve",
    "animali domestici": "Pet Care",
    "pet care": "Pet Care",
    "latte, burro, uova e yogurt": "Latticini",
    "latticini": "Latticini",
    "surgelati e gelati": "Surgelati",
    "surgelati": "Surgelati",
    "birre e liquori": "Alcolici",
    "vini, spumanti e champagne": "Alcolici",
    "alcolici": "Alcolici",
    "acqua, bibite, succhi e aperitivi": "Bevande",
    "bevande": "Bevande",
    "pasta e riso, farina e preparati": "Pasta e Riso",
    "pasta e riso": "Pasta e Riso",
    "pane e snack salati": "Pane e Cereali",
    "pane e cereali": "Pane e Cereali",
    "caffè, infusi e zucchero": "Caffe e Te",
    "caffe e te": "Caffe e Te",
    "carne e pesce": "Carne",
    "carne": "Carne",
    "pesce": "Pesce",
    "gastronomia": "Gastronomia",
    "neonati e infanzia": "Neonati e Infanzia",
    "acqua": "Bevande",
    "uova": "Latticini",
    "altro": "Altro",
}

# Categories to exclude (catch-all, seasonal, non-food)
_CATEGORY_EXCLUDE = {
    "supermercato", "pasqua", "videogiochi", "console",
    "action figure", "cancelleria", "giocattoli", "elettronica",
    "telefonia", "informatica", "giardinaggio", "auto e moto",
}

# MaterialCommunityIcons name per canonical category
_CATEGORY_ICONS: dict[str, str] = {
    "Carne": "food-steak",
    "Latticini": "cow",
    "Bevande": "bottle-soda-classic",
    "Surgelati": "snowflake",
    "Frutta e Verdura": "fruit-watermelon",
    "Pesce": "fish",
    "Dolci e Snack": "candy",
    "Igiene e Cura Persona": "hand-wash",
    "Pulizia Casa": "spray-bottle",
    "Pasta e Riso": "pasta",
    "Condimenti e Conserve": "shaker",
    "Salumi e Formaggi": "cheese",
    "Caffe e Te": "coffee",
    "Alcolici": "glass-wine",
    "Pane e Cereali": "bread-slice",
    "Pet Care": "paw",
    "Gastronomia": "food-turkey",
    "Benessere e Intolleranze": "leaf",
    "Neonati e Infanzia": "baby-carriage",
    "Altro": "dots-horizontal",
}


def _normalize_category(raw: str | None) -> str | None:
    """Map a raw product category to its canonical display name."""
    if not raw:
        return None
    key = raw.lower().strip()
    if key in _CATEGORY_EXCLUDE:
        return None
    canonical = _CATEGORY_NORM.get(key)
    if canonical:
        return canonical
    # If raw name matches a canonical name directly (case-insensitive), keep it
    for canon in _CATEGORY_ICONS:
        if key == canon.lower():
            return canon
    return raw.strip()  # keep as-is if not mapped


def _reverse_category_lookup(canonical: str) -> list[str]:
    """Return all raw category keys (lowercased) that map to the given canonical name."""
    variants = []
    for raw_key, canon in _CATEGORY_NORM.items():
        if canon == canonical:
            variants.append(raw_key)
    # Also include the canonical name itself (lowercased)
    variants.append(canonical.lower())
    return list(set(variants))


class CatalogHomeCategoryResponse(BaseModel):
    name: str
    slug: str
    icon: str
    count: int
    offers: list  # Will contain OfferResponse dicts


class CatalogHomeResponse(BaseModel):
    featured: list  # Will contain OfferResponse dicts
    categories: list[CatalogHomeCategoryResponse]


@router.get("/catalog-home")
async def get_catalog_home(
    db: AsyncSession = Depends(get_db),
):
    """Home feed for catalog tab: featured offers + per-category sections."""
    from app.api.offers import OfferResponse, _build_offer_responses, _get_previous_prices

    today = date.today()

    # ── 1. Aggregate product counts by normalised category ──
    cat_query = select(Product.category, func.count()).group_by(Product.category)
    cat_result = await db.execute(cat_query)
    cat_counts: dict[str, int] = defaultdict(int)
    cat_raw_variants: dict[str, set[str]] = defaultdict(set)  # canonical → set of raw names

    for raw_cat, cnt in cat_result.all():
        canonical = _normalize_category(raw_cat)
        if not canonical:
            continue
        cat_counts[canonical] += cnt
        cat_raw_variants[canonical].add(raw_cat)

    # Top 20 categories with >10 products
    top_categories = sorted(
        [(name, count) for name, count in cat_counts.items() if count > 10],
        key=lambda x: -x[1],
    )[:20]

    # ── 2. Featured offers (top 8 by discount) ──
    feat_query = (
        select(Offer)
        .options(joinedload(Offer.product), joinedload(Offer.chain))
        .where(
            Offer.valid_from <= today,
            Offer.valid_to >= today,
            Offer.discount_pct.is_not(None),
        )
        .order_by(Offer.discount_pct.desc())
        .limit(8)
    )
    feat_result = await db.execute(feat_query)
    featured_offers = feat_result.unique().scalars().all()

    feat_pids = [o.product_id for o in featured_offers]
    feat_dates = {o.product_id: o.valid_from for o in featured_offers if o.valid_from}
    feat_prev = await _get_previous_prices(feat_pids, feat_dates, db)
    featured_data = _build_offer_responses(featured_offers, feat_prev)

    # ── 3. Per-category top 6 offers ──
    categories_data = []
    for cat_name, cat_count in top_categories:
        # Get all raw variants for this normalised category
        raw_variants = cat_raw_variants.get(cat_name, {cat_name})
        variant_filters = [Product.category.ilike(v) for v in raw_variants]

        cat_offer_query = (
            select(Offer)
            .options(joinedload(Offer.product), joinedload(Offer.chain))
            .join(Offer.product)
            .where(
                Offer.valid_from <= today,
                Offer.valid_to >= today,
                Offer.discount_pct.is_not(None),
                or_(*variant_filters),
            )
            .order_by(Offer.discount_pct.desc())
            .limit(6)
        )
        cat_offer_result = await db.execute(cat_offer_query)
        cat_offers = cat_offer_result.unique().scalars().all()

        if not cat_offers:
            continue

        co_pids = [o.product_id for o in cat_offers]
        co_dates = {o.product_id: o.valid_from for o in cat_offers if o.valid_from}
        co_prev = await _get_previous_prices(co_pids, co_dates, db)
        offers_data = _build_offer_responses(cat_offers, co_prev)

        slug = cat_name.lower().replace(" ", "-").replace("'", "")
        icon = _CATEGORY_ICONS.get(cat_name, "tag-outline")

        categories_data.append({
            "name": cat_name,
            "slug": slug,
            "icon": icon,
            "count": cat_count,
            "offers": [o.model_dump(mode="json") for o in offers_data],
        })

    return {
        "featured": [o.model_dump(mode="json") for o in featured_data],
        "categories": categories_data,
    }


@router.get("/catalog-grouped")
async def get_catalog_grouped(
    category: str | None = Query(None),
    brand: str | None = Query(None),
    q: str | None = Query(None),
    sort: str | None = Query(None, enum=["name", "price", "price_per_unit"]),
    chain: str | None = Query(None, description="Comma-separated chain slugs"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Browse catalog with offers grouped per product (pre-pagination grouping).

    Groups ALL matching products first, then paginates on groups.
    Products without active offers are returned last with last-known price info.
    """
    today = date.today()
    from app.services.price_analyzer import PriceAnalyzer

    chain_slugs: list[str] = []
    if chain:
        chain_slugs = [s.strip() for s in chain.split(",")]

    # ── 1. Fetch ALL matching product tuples (lightweight) ──
    prod_query = select(
        Product.id, Product.name, Product.brand, Product.category, Product.barcode
    )
    if category:
        # Check if this is a normalised category name → search all raw variants
        variants = _reverse_category_lookup(category)
        if len(variants) > 1:
            prod_query = prod_query.where(
                or_(*[Product.category.ilike(v) for v in variants])
            )
        else:
            prod_query = prod_query.where(Product.category.ilike(category))
    if brand:
        prod_query = prod_query.where(Product.brand.ilike(f"%{brand}%"))
    if q:
        for cond in _build_search_filter(q):
            prod_query = prod_query.where(cond)

    # When chain filter is active, only include products with offers in that chain
    if chain_slugs:
        chain_ids_sq = select(Chain.id).where(Chain.slug.in_(chain_slugs))
        has_offer_sq = (
            select(Offer.product_id)
            .where(
                Offer.valid_from <= today,
                Offer.valid_to >= today,
                Offer.chain_id.in_(chain_ids_sq),
            )
            .distinct()
        )
        prod_query = prod_query.where(Product.id.in_(has_offer_sq))

    prod_query = prod_query.order_by(Product.name)
    result = await db.execute(prod_query)
    all_rows: list[_ProductTuple] = [
        (row.id, row.name, row.brand, row.category, row.barcode)
        for row in result.all()
    ]

    # Fuzzy fallback: if ILIKE found nothing and query is >= 3 chars, try pg_trgm
    if not all_rows and q and len(q.strip()) >= 3:
        fuzzy_products = await _fuzzy_search_products(q, db, limit=limit, category=category)
        if fuzzy_products:
            all_rows = [
                (p.id, p.name, p.brand, p.category, p.barcode)
                for p in fuzzy_products
            ]

    if not all_rows:
        return []

    # ── 2. Group similar products (pre-pagination) ──
    id_groups = _group_similar_product_ids(all_rows)

    # ── 3. Determine which groups have active offers ──
    all_ids = [r[0] for r in all_rows]
    active_offer_pids_result = await db.execute(
        select(Offer.product_id)
        .where(
            Offer.product_id.in_(all_ids),
            Offer.valid_from <= today,
            Offer.valid_to >= today,
        )
        .distinct()
    )
    active_offer_pids: set[uuid.UUID] = set(active_offer_pids_result.scalars().all())

    groups_with_offers: list[list[uuid.UUID]] = []
    groups_without_offers: list[list[uuid.UUID]] = []
    for grp in id_groups:
        if any(pid in active_offer_pids for pid in grp):
            groups_with_offers.append(grp)
        else:
            groups_without_offers.append(grp)

    # ── 4. Sort and paginate on groups ──
    # Active-offer groups first, then inactive
    sorted_groups = groups_with_offers + groups_without_offers
    total_groups = len(sorted_groups)
    page_groups = sorted_groups[offset : offset + limit]

    if not page_groups:
        return []

    # ── 5. Hydrate only the page's products ──
    page_ids: list[uuid.UUID] = []
    for grp in page_groups:
        page_ids.extend(grp)
    page_id_set = set(page_ids)

    products_result = await db.execute(
        select(Product).where(Product.id.in_(page_ids))
    )
    products_by_id: dict[uuid.UUID, Product] = {
        p.id: p for p in products_result.scalars().all()
    }

    # ── 6. Fetch active offers for page products ──
    offers_where = [
        Offer.product_id.in_(page_ids),
        Offer.valid_from <= today,
        Offer.valid_to >= today,
    ]
    if chain_slugs:
        offers_where.append(
            Offer.chain_id.in_(select(Chain.id).where(Chain.slug.in_(chain_slugs)))
        )

    offers_result = await db.execute(
        select(Offer)
        .options(joinedload(Offer.chain))
        .where(*offers_where)
        .order_by(
            Offer.product_id,
            Offer.price_per_unit.asc().nulls_last(),
            Offer.offer_price.asc(),
        )
    )
    all_offers = offers_result.unique().scalars().all()

    offers_by_product: dict[uuid.UUID, list[Offer]] = defaultdict(list)
    for o in all_offers:
        offers_by_product[o.product_id].append(o)

    # ── 7. Fetch last-known price for products without active offers ──
    no_offer_ids = [pid for pid in page_ids if pid not in active_offer_pids]
    last_known: dict[uuid.UUID, tuple[Decimal, str, date]] = {}
    if no_offer_ids:
        # Get the most recent expired offer per product
        from sqlalchemy import desc
        last_offer_result = await db.execute(
            select(Offer)
            .options(joinedload(Offer.chain))
            .where(Offer.product_id.in_(no_offer_ids))
            .order_by(Offer.product_id, desc(Offer.valid_to))
        )
        last_offers = last_offer_result.unique().scalars().all()
        for lo in last_offers:
            if lo.product_id not in last_known:
                last_known[lo.product_id] = (
                    lo.offer_price,
                    lo.chain.name if lo.chain else "Sconosciuto",
                    lo.valid_to or lo.valid_from,
                )

    # ── 8. Compute price indicators ──
    ids_with_offers = [pid for pid in page_ids if pid in offers_by_product]
    analyzer = PriceAnalyzer()
    indicators = (
        await analyzer.compute_indicators_batch(ids_with_offers, session=db)
        if ids_with_offers
        else {}
    )

    # ── 9. Build results – one SmartSearchResult per group ──
    results: list[SmartSearchResult] = []
    for grp in page_groups:
        # Representative product = first by name
        group_products = [products_by_id[pid] for pid in grp if pid in products_by_id]
        if not group_products:
            continue
        group_products.sort(key=lambda p: p.name)
        representative = group_products[0]

        # Merge offers from all products in the group
        merged_offers: list[Offer] = []
        for p in group_products:
            merged_offers.extend(offers_by_product.get(p.id, []))

        # Sort merged offers by price
        merged_offers.sort(key=lambda o: (o.offer_price, o.price_per_unit or 0))

        # Use best indicator from the group
        best_indicator = None
        for p in group_products:
            ind = indicators.get(p.id)
            if ind == "top":
                best_indicator = "top"
                break
            if ind and not best_indicator:
                best_indicator = ind

        # Use image from any product in the group if representative lacks one
        if not representative.image_url:
            for p in group_products:
                if p.image_url:
                    representative.image_url = p.image_url
                    break

        # Last-known price for groups without active offers
        lk_price, lk_chain, lk_date = None, None, None
        if not merged_offers:
            for pid in grp:
                if pid in last_known:
                    lk_price, lk_chain, lk_date = last_known[pid]
                    break

        results.append(
            _build_smart_result(
                representative, merged_offers, best_indicator,
                last_known_price=lk_price,
                last_known_chain=lk_chain,
                last_seen_date=lk_date,
            )
        )

    # Sort results based on sort param (within the active/inactive sections)
    if sort == "price":
        # Keep active-first ordering, sort within each section
        active = [r for r in results if r.has_active_offers]
        inactive = [r for r in results if not r.has_active_offers]
        active.sort(
            key=lambda r: min((o.offer_price for o in r.offers), default=Decimal("9999"))
        )
        inactive.sort(
            key=lambda r: r.last_known_price or Decimal("9999")
        )
        results = active + inactive
    elif sort == "price_per_unit":
        active = [r for r in results if r.has_active_offers]
        inactive = [r for r in results if not r.has_active_offers]
        active.sort(
            key=lambda r: r.best_price_per_unit or Decimal("9999")
        )
        results = active + inactive

    return results


class BrandInfoResponse(BaseModel):
    name: str
    count: int


@router.get("/brands", response_model=list[BrandInfoResponse])
async def get_brands(
    q: str | None = Query(None, min_length=2),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Return distinct product brands with counts, optionally filtered by query."""
    query = (
        select(Product.brand, func.count(Product.id).label("count"))
        .where(Product.brand.isnot(None), Product.brand != "")
    )
    if q:
        query = query.where(Product.brand.ilike(f"%{q}%"))
    query = query.group_by(Product.brand).order_by(func.count(Product.id).desc()).limit(limit)

    result = await db.execute(query)
    rows = result.all()
    return [BrandInfoResponse(name=name, count=count) for name, count in rows]


@router.get("/categories", response_model=list[CategoryResponse])
async def get_categories(
    db: AsyncSession = Depends(get_db),
):
    """Return distinct product categories with counts."""
    result = await db.execute(
        select(Product.category, func.count(Product.id).label("count"))
        .where(Product.category.isnot(None), Product.category != "")
        .group_by(Product.category)
        .order_by(Product.category)
    )
    rows = result.all()
    return [CategoryResponse(name=name, count=count) for name, count in rows]


@router.get("/categories/tree", response_model=list[CategoryTree])
async def get_categories_tree(
    db: AsyncSession = Depends(get_db),
):
    """Return hierarchical category tree with product counts."""
    # Fetch all categories (parents + children)
    cat_result = await db.execute(
        select(Category).order_by(Category.sort_order)
    )
    all_cats = cat_result.scalars().all()

    # Product counts per category name
    count_result = await db.execute(
        select(Product.category, func.count(Product.id))
        .where(Product.category.isnot(None), Product.category != "")
        .group_by(Product.category)
    )
    counts = dict(count_result.all())

    # Build tree
    parents = [c for c in all_cats if c.parent_id is None]
    children_by_parent: dict[uuid.UUID, list[Category]] = defaultdict(list)
    for c in all_cats:
        if c.parent_id is not None:
            children_by_parent[c.parent_id].append(c)

    tree: list[CategoryTree] = []
    for parent in parents:
        tree.append(CategoryTree(
            id=str(parent.id),
            name=parent.name,
            slug=parent.slug,
            icon=parent.icon,
            count=counts.get(parent.name, 0),
            children=[
                CategoryChild(id=str(ch.id), name=ch.name, slug=ch.slug, icon=ch.icon)
                for ch in children_by_parent.get(parent.id, [])
            ],
        ))
    return tree


class SmartSearchOfferResponse(BaseModel):
    chain_name: str
    chain_slug: str
    offer_price: Decimal
    original_price: Decimal | None
    discount_pct: Decimal | None
    price_per_unit: Decimal | None
    unit_reference: str | None
    valid_to: date | None
    offer_id: uuid.UUID


class SmartSearchResult(BaseModel):
    product: ProductResponse
    offers: list[SmartSearchOfferResponse]
    price_indicator: str | None = None
    best_price_per_unit: Decimal | None = None
    unit_reference: str | None = None
    is_category_match: bool = False
    has_active_offers: bool = True
    last_known_price: Decimal | None = None
    last_known_chain: str | None = None
    last_seen_date: date | None = None


FRESH_CATEGORIES = {
    "Formaggi", "Salumi", "Carne", "Pesce", "Frutta",
    "Verdura", "Latticini", "Gastronomia",
}


def _build_smart_result(
    product: Product,
    raw_offers: list[Offer],
    indicator: str | None,
    is_category_match: bool = False,
    last_known_price: Decimal | None = None,
    last_known_chain: str | None = None,
    last_seen_date: date | None = None,
) -> SmartSearchResult:
    """Build a SmartSearchResult from a product and its offers."""
    seen_chains: set[uuid.UUID] = set()
    best_per_chain: list[Offer] = []
    for o in raw_offers:
        if o.chain_id not in seen_chains:
            seen_chains.add(o.chain_id)
            best_per_chain.append(o)

    ppus = [o.price_per_unit for o in best_per_chain if o.price_per_unit is not None]
    best_ppu = min(ppus) if ppus else None
    unit_refs = [o.unit_reference for o in best_per_chain if o.unit_reference]
    unit_ref = unit_refs[0] if unit_refs else None

    return SmartSearchResult(
        product=ProductResponse.model_validate(product),
        offers=[
            SmartSearchOfferResponse(
                chain_name=o.chain.name if o.chain else "Unknown",
                chain_slug=o.chain.slug if o.chain else "",
                offer_price=o.offer_price,
                original_price=o.original_price,
                discount_pct=o.discount_pct,
                price_per_unit=o.price_per_unit,
                unit_reference=o.unit_reference,
                valid_to=o.valid_to,
                offer_id=o.id,
            )
            for o in best_per_chain
        ],
        price_indicator=indicator,
        best_price_per_unit=best_ppu,
        unit_reference=unit_ref,
        is_category_match=is_category_match,
        has_active_offers=len(best_per_chain) > 0,
        last_known_price=last_known_price,
        last_known_chain=last_known_chain,
        last_seen_date=last_seen_date,
    )


@router.get("/smart-search", response_model=list[SmartSearchResult])
async def smart_search(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(10, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Combined search + multi-chain compare in a single efficient query.

    Returns up to `limit` direct matches, plus up to 5 category-match
    products from the same fresh subcategory (appended separately).
    """
    today = date.today()
    from collections import defaultdict
    from app.services.price_analyzer import PriceAnalyzer

    # Find matching products — direct matches only (with synonym expansion)
    smart_query = select(Product)
    for cond in _build_search_filter(q):
        smart_query = smart_query.where(cond)
    prod_result = await db.execute(
        smart_query.order_by(Product.name).limit(limit)
    )
    products = list(prod_result.scalars().all())

    # Fallback to pg_trgm fuzzy search if no ILIKE results
    if not products:
        products = await _fuzzy_search_products(q, db, limit=limit)

    if not products:
        return []

    product_ids = [p.id for p in products]

    # Category-match: only add a few fresh-category alternatives as extras
    fresh_subcategories: set[str] = set()
    for p in products:
        if p.category and p.category in FRESH_CATEGORIES and p.subcategory:
            fresh_subcategories.add(p.subcategory)

    category_products: list[Product] = []
    if fresh_subcategories:
        cat_result = await db.execute(
            select(Product)
            .where(
                Product.subcategory.in_(fresh_subcategories),
                Product.id.notin_(product_ids),
            )
            .order_by(Product.name)
            .limit(5)
        )
        category_products = list(cat_result.scalars().all())
        product_ids.extend([p.id for p in category_products])

    # Fetch all active offers in one query
    offers_result = await db.execute(
        select(Offer)
        .options(joinedload(Offer.chain))
        .where(
            Offer.product_id.in_(product_ids),
            Offer.valid_from <= today,
            Offer.valid_to >= today,
        )
        .order_by(Offer.product_id, Offer.price_per_unit.asc().nulls_last(), Offer.offer_price.asc())
    )
    all_offers = offers_result.unique().scalars().all()

    offers_by_product: dict[uuid.UUID, list[Offer]] = defaultdict(list)
    for o in all_offers:
        offers_by_product[o.product_id].append(o)

    # Compute indicators
    analyzer = PriceAnalyzer()
    indicators = await analyzer.compute_indicators_batch(product_ids, session=db)

    results = []

    # Direct matches first (up to limit)
    for product in products:
        results.append(
            _build_smart_result(
                product,
                offers_by_product.get(product.id, []),
                indicators.get(product.id),
            )
        )

    # Category matches appended as extras (max 5, only if they have offers)
    for product in category_products:
        offers = offers_by_product.get(product.id, [])
        if offers:
            results.append(
                _build_smart_result(
                    product,
                    offers,
                    indicators.get(product.id),
                    is_category_match=True,
                )
            )

    return results


@router.get("/search", response_model=list[ProductSearchResult])
async def search_products(
    q: str = Query(..., min_length=2, description="Search query"),
    category: str | None = Query(None),
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
):
    # Try ILIKE first (with synonym expansion)
    expanded = _expand_synonyms(q)
    query = select(Product).where(
        Product.name.ilike(f"%{expanded}%")
    )
    if category:
        query = query.where(Product.category.ilike(f"%{category}%"))
    query = query.limit(limit)
    result = await db.execute(query)
    products = list(result.scalars().all())

    # Fallback to pg_trgm fuzzy search if no ILIKE results
    if not products:
        products = await _fuzzy_search_products(q, db, limit=limit, category=category)

    results = []
    today = date.today()
    for p in products:
        # Find best current offer
        offer_result = await db.execute(
            select(Offer)
            .options(joinedload(Offer.chain))
            .where(
                Offer.product_id == p.id,
                Offer.valid_from <= today,
                Offer.valid_to >= today,
            )
            .order_by(Offer.offer_price)
            .limit(1)
        )
        best_offer = offer_result.unique().scalar_one_or_none()

        # Count active offers
        count_result = await db.execute(
            select(func.count(Offer.id)).where(
                Offer.product_id == p.id,
                Offer.valid_from <= today,
                Offer.valid_to >= today,
            )
        )
        count = count_result.scalar()

        results.append(
            ProductSearchResult(
                product=ProductResponse.model_validate(p),
                best_current_price=best_offer.offer_price if best_offer else None,
                chain_name=best_offer.chain.name if best_offer and best_offer.chain else None,
                offers_count=count or 0,
            )
        )

    return results


@router.get("/barcode/{ean}", response_model=SmartSearchResult)
async def get_product_by_barcode(ean: str, db: AsyncSession = Depends(get_db)):
    """Look up a product by barcode (EAN) and return it with offers."""
    result = await db.execute(
        select(Product).where(Product.barcode == ean)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found for this barcode")

    today = date.today()
    offers_result = await db.execute(
        select(Offer)
        .options(joinedload(Offer.chain))
        .where(
            Offer.product_id == product.id,
            Offer.valid_from <= today,
            Offer.valid_to >= today,
        )
        .order_by(Offer.offer_price)
    )
    offers = offers_result.unique().scalars().all()

    from app.services.price_analyzer import PriceAnalyzer
    analyzer = PriceAnalyzer()
    indicator = await analyzer.get_indicator(product.id, db) if offers else None

    return _build_smart_result(product, list(offers), indicator)


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(product_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.get("/{product_id}/history", response_model=PriceHistoryResponse)
async def get_price_history(
    product_id: uuid.UUID,
    months: int = Query(6, description="Months of history"),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    offers_result = await db.execute(
        select(Offer)
        .options(joinedload(Offer.chain))
        .where(Offer.product_id == product_id)
        .order_by(Offer.valid_from.desc())
        .limit(100)
    )
    offers = offers_result.unique().scalars().all()

    history = [
        PriceHistoryPoint(
            date=o.valid_from or o.created_at.date(),
            price=o.offer_price,
            chain_name=o.chain.name if o.chain else "Unknown",
            chain_slug=o.chain.slug if o.chain else None,
            discount_type=o.discount_type,
            price_per_unit=o.price_per_unit,
            unit_reference=o.unit_reference,
        )
        for o in offers
    ]

    return PriceHistoryResponse(
        product=ProductResponse.model_validate(product),
        history=history,
    )


@router.get("/{product_id}/best-price", response_model=BestPriceResponse)
async def get_best_price(
    product_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    today = date.today()
    product_ids = await _find_similar_ids(product, db)

    offer_result = await db.execute(
        select(Offer)
        .options(joinedload(Offer.chain))
        .where(
            Offer.product_id.in_(product_ids),
            Offer.valid_from <= today,
            Offer.valid_to >= today,
        )
        .order_by(Offer.offer_price)
        .limit(1)
    )
    best = offer_result.unique().scalar_one_or_none()
    if not best:
        raise HTTPException(status_code=404, detail="No active offers found")

    from app.services.price_analyzer import PriceAnalyzer

    analyzer = PriceAnalyzer()
    indicator = await analyzer.get_price_indicator(
        product_id,
        offer_price=best.offer_price,
        offer_ppu=best.price_per_unit,
        session=db,
    )

    return BestPriceResponse(
        product=ProductResponse.model_validate(product),
        best_price=best.offer_price,
        chain_name=best.chain.name if best.chain else "Unknown",
        valid_until=best.valid_to,
        original_price=best.original_price,
        discount_pct=best.discount_pct,
        price_per_unit=best.price_per_unit,
        unit_reference=best.unit_reference,
        price_indicator=indicator,
    )


class CompareOfferResponse(BaseModel):
    chain_name: str
    chain_slug: str
    product_name: str
    product_image_url: str | None
    offer_price: Decimal
    original_price: Decimal | None
    discount_pct: Decimal | None
    price_per_unit: Decimal | None
    unit_reference: str | None
    valid_to: date | None
    offer_id: uuid.UUID


class CompareResponse(BaseModel):
    product: ProductResponse
    offers: list[CompareOfferResponse]


@router.get("/{product_id}/compare", response_model=CompareResponse)
async def compare_prices(
    product_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    """Return the best active offer per chain for a product.

    Also includes offers from similar products (fuzzy name match) across
    different chains so the user sees a full multi-chain comparison.
    """
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    today = date.today()
    product_ids = await _find_similar_ids(product, db)

    # Get all active offers for this product + similar products
    offers_result = await db.execute(
        select(Offer)
        .options(joinedload(Offer.chain), joinedload(Offer.product))
        .where(
            Offer.product_id.in_(product_ids),
            Offer.valid_from <= today,
            Offer.valid_to >= today,
        )
        .order_by(Offer.offer_price)
    )
    all_offers = offers_result.unique().scalars().all()

    # Keep only the cheapest per chain
    seen_chains: set[uuid.UUID] = set()
    best_per_chain: list[Offer] = []
    for o in all_offers:
        if o.chain_id not in seen_chains:
            seen_chains.add(o.chain_id)
            best_per_chain.append(o)

    return CompareResponse(
        product=ProductResponse.model_validate(product),
        offers=[
            CompareOfferResponse(
                chain_name=o.chain.name if o.chain else "Unknown",
                chain_slug=o.chain.slug if o.chain else "",
                product_name=o.product.name if o.product else "",
                product_image_url=o.product.image_url if o.product else None,
                offer_price=o.offer_price,
                original_price=o.original_price,
                discount_pct=o.discount_pct,
                price_per_unit=o.price_per_unit,
                unit_reference=o.unit_reference,
                valid_to=o.valid_to,
                offer_id=o.id,
            )
            for o in best_per_chain
        ],
    )


class PriceTrendPoint(BaseModel):
    period: str
    avg_price_per_unit: Decimal | None = None
    min_price_per_unit: Decimal | None = None
    max_price_per_unit: Decimal | None = None
    avg_offer_price: Decimal | None = None
    min_offer_price: Decimal | None = None
    max_offer_price: Decimal | None = None
    data_points: int = 0


class PriceTrendResponse(BaseModel):
    product: ProductResponse
    trends: list[PriceTrendPoint]
    unit_reference: str | None = None


@router.get("/{product_id}/price-trends", response_model=PriceTrendResponse)
async def get_price_trends(
    product_id: uuid.UUID,
    months: int = Query(12, ge=1, le=36, description="Months of trend data"),
    db: AsyncSession = Depends(get_db),
):
    """Return monthly aggregated price trends for a product."""
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    since = date.today() - timedelta(days=months * 31)

    period_expr = func.to_char(
        func.date_trunc("month", Offer.valid_from), "YYYY-MM"
    )

    trend_query = (
        select(
            period_expr.label("period"),
            func.avg(Offer.price_per_unit).label("avg_ppu"),
            func.min(Offer.price_per_unit).label("min_ppu"),
            func.max(Offer.price_per_unit).label("max_ppu"),
            func.avg(Offer.offer_price).label("avg_price"),
            func.min(Offer.offer_price).label("min_price"),
            func.max(Offer.offer_price).label("max_price"),
            func.count(Offer.id).label("cnt"),
        )
        .where(
            Offer.product_id == product_id,
            Offer.valid_from >= since,
            Offer.valid_from.isnot(None),
        )
        .group_by(period_expr)
        .order_by(period_expr)
    )
    trend_result = await db.execute(trend_query)
    rows = trend_result.all()

    # Determine the dominant unit_reference for this product
    unit_ref_result = await db.execute(
        select(Offer.unit_reference)
        .where(
            Offer.product_id == product_id,
            Offer.unit_reference.isnot(None),
        )
        .group_by(Offer.unit_reference)
        .order_by(func.count(Offer.id).desc())
        .limit(1)
    )
    unit_ref = unit_ref_result.scalar_one_or_none()

    trends = [
        PriceTrendPoint(
            period=row.period,
            avg_price_per_unit=round(row.avg_ppu, 2) if row.avg_ppu else None,
            min_price_per_unit=row.min_ppu,
            max_price_per_unit=row.max_ppu,
            avg_offer_price=round(row.avg_price, 2) if row.avg_price else None,
            min_offer_price=row.min_price,
            max_offer_price=row.max_price,
            data_points=row.cnt,
        )
        for row in rows
    ]

    return PriceTrendResponse(
        product=ProductResponse.model_validate(product),
        trends=trends,
        unit_reference=unit_ref,
    )
