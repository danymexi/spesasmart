"""API routes for products."""

import re
import uuid
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from difflib import SequenceMatcher

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from sqlalchemy import or_

from app.database import get_db
from app.models import Chain, Offer, Product

router = APIRouter(prefix="/products", tags=["products"])


def _build_search_filter(q: str):
    """Build a search filter that matches each word against name OR brand.

    "latte valtellina" → name+brand must contain both "latte" AND "valtellina"
    (each word can be in either field).
    """
    words = q.strip().split()
    conditions = []
    for word in words:
        pattern = f"%{word}%"
        conditions.append(or_(Product.name.ilike(pattern), Product.brand.ilike(pattern)))
    return conditions


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
    """Normalize a product name for fuzzy grouping."""
    n = name.lower().strip()
    # Remove common quantity/size suffixes and trailing numbers
    n = re.sub(r"\b\d+\s*(pz|pezzi|rotoli|x|ml|cl|l|g|kg|gr)\b", "", n)
    n = re.sub(r"\bx\s*\d+\b", "", n)
    # Remove "carta igienica", "carta cucina" etc. (generic product type)
    n = re.sub(r"\bcarta\s+(igienica|cucina|assorbente)\b", "", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


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


def _group_similar_products(products: list[Product]) -> list[list[Product]]:
    """Group products with similar names.

    Brand check is soft BUT only for descriptive names (>=3 words).
    Short/generic names like "Vaniglia" ALWAYS require matching brand
    because they could refer to completely different products (biscuits,
    yogurt, protein drink, etc.).
    """
    groups: list[list[Product]] = []
    used: set[int] = set()
    normalized = [_normalize_product_name(p.name) for p in products]

    for i, p in enumerate(products):
        if i in used:
            continue
        group = [p]
        used.add(i)
        brand_i = (p.brand or "").lower().strip()
        for j in range(i + 1, len(products)):
            if j in used:
                continue
            q = products[j]
            brand_j = (q.brand or "").lower().strip()
            brands_differ = brand_i and brand_j and brand_i != brand_j

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


def _is_similar_product(
    prod_norm: str, prod_brand: str,
    candidate_norm: str, candidate_brand: str,
) -> bool:
    """Check if a candidate product is similar enough to group with prod."""
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
    product_ids = [product.id]
    words = product.name.split()
    keyword = None
    for w in words:
        if len(w) >= 4 and w.lower() not in (
            "alla", "allo", "alle", "della", "dello", "delle", "con", "per",
        ):
            keyword = w
            break
    if not keyword:
        return product_ids

    prod_norm = _normalize_product_name(product.name)
    prod_brand = (product.brand or "").lower().strip()
    cands = await db.execute(
        select(Product).where(
            Product.name.ilike(f"%{keyword}%"),
            Product.id != product.id,
        )
    )
    for cp in cands.scalars().all():
        cp_norm = _normalize_product_name(cp.name)
        cp_brand = (cp.brand or "").lower().strip()
        if _is_similar_product(prod_norm, prod_brand, cp_norm, cp_brand):
            product_ids.append(cp.id)
    return product_ids


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
    """Browse catalog with offers grouped per product (fuzzy name matching)."""
    today = date.today()
    from app.services.price_analyzer import PriceAnalyzer

    # ── 1. Fetch products using same filters as /catalog ──
    prod_query = select(Product)
    if category:
        prod_query = prod_query.where(Product.category.ilike(category))
    if brand:
        prod_query = prod_query.where(Product.brand.ilike(f"%{brand}%"))
    if q:
        for cond in _build_search_filter(q):
            prod_query = prod_query.where(cond)

    # If chain filter, only products that have an active offer in that chain
    if chain:
        chain_slugs = [s.strip() for s in chain.split(",")]
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

    prod_query = prod_query.order_by(Product.name).offset(offset).limit(limit)
    result = await db.execute(prod_query)
    products = list(result.scalars().all())

    if not products:
        return []

    # ── 2. Group similar products by fuzzy name matching ──
    groups = _group_similar_products(products)

    # Collect all product IDs across all groups
    all_product_ids = [p.id for p in products]

    # ── 3. Fetch ALL active offers for these products in one query ──
    offers_where = [
        Offer.product_id.in_(all_product_ids),
        Offer.valid_from <= today,
        Offer.valid_to >= today,
    ]
    if chain:
        chain_slugs = [s.strip() for s in chain.split(",")]
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

    # ── 4. Compute price indicators ──
    ids_with_offers = [pid for pid in all_product_ids if pid in offers_by_product]
    analyzer = PriceAnalyzer()
    indicators = (
        await analyzer.compute_indicators_batch(ids_with_offers, session=db)
        if ids_with_offers
        else {}
    )

    # ── 5. Build results – one SmartSearchResult per group ──
    results: list[SmartSearchResult] = []
    for group in groups:
        # Representative product = first in group (alphabetical)
        representative = group[0]
        # Merge offers from all products in the group
        group_ids = {p.id for p in group}
        merged_offers: list[Offer] = []
        for p in group:
            merged_offers.extend(offers_by_product.get(p.id, []))

        # If no offers found in the group, look for offers from similar products
        # (aligns list view with detail/best-price view which uses _find_similar_ids)
        if not merged_offers:
            similar_ids = await _find_similar_ids(representative, db)
            extra_ids = [sid for sid in similar_ids if sid not in group_ids]
            if extra_ids:
                extra_where = [
                    Offer.product_id.in_(extra_ids),
                    Offer.valid_from <= today,
                    Offer.valid_to >= today,
                ]
                if chain:
                    extra_where.append(
                        Offer.chain_id.in_(
                            select(Chain.id).where(Chain.slug.in_(chain_slugs))
                        )
                    )
                extra_result = await db.execute(
                    select(Offer)
                    .options(joinedload(Offer.chain))
                    .where(*extra_where)
                    .order_by(Offer.offer_price.asc())
                )
                merged_offers = list(extra_result.unique().scalars().all())

        # Sort merged offers by price
        merged_offers.sort(key=lambda o: (o.offer_price, o.price_per_unit or 0))
        # Use best indicator from the group
        best_indicator = None
        for p in group:
            ind = indicators.get(p.id)
            if ind == "top":
                best_indicator = "top"
                break
            if ind and not best_indicator:
                best_indicator = ind

        # Use image from any product in the group if representative lacks one
        if not representative.image_url:
            for p in group:
                if p.image_url:
                    representative.image_url = p.image_url
                    break

        results.append(
            _build_smart_result(representative, merged_offers, best_indicator)
        )

    # Sort results based on sort param
    if sort == "price":
        results.sort(
            key=lambda r: min((o.offer_price for o in r.offers), default=Decimal("9999"))
        )
    elif sort == "price_per_unit":
        results.sort(
            key=lambda r: r.best_price_per_unit or Decimal("9999")
        )

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


FRESH_CATEGORIES = {
    "Formaggi", "Salumi", "Carne", "Pesce", "Frutta",
    "Verdura", "Latticini", "Gastronomia",
}


def _build_smart_result(
    product: Product,
    raw_offers: list[Offer],
    indicator: str | None,
    is_category_match: bool = False,
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

    # Find matching products — direct matches only
    smart_query = select(Product)
    for cond in _build_search_filter(q):
        smart_query = smart_query.where(cond)
    prod_result = await db.execute(
        smart_query.order_by(Product.name).limit(limit)
    )
    products = list(prod_result.scalars().all())

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
    query = select(Product).where(
        Product.name.ilike(f"%{q}%")
    )
    if category:
        query = query.where(Product.category.ilike(f"%{category}%"))
    query = query.limit(limit)
    result = await db.execute(query)
    products = result.scalars().all()

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
        .options(joinedload(Offer.chain))
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
