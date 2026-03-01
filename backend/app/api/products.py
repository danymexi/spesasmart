"""API routes for products."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models import Chain, Offer, Product

router = APIRouter(prefix="/products", tags=["products"])


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


class CategoryResponse(BaseModel):
    name: str
    count: int


class PriceHistoryPoint(BaseModel):
    date: date
    price: Decimal
    chain_name: str
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


class ProductSearchResult(BaseModel):
    product: ProductResponse
    best_current_price: Decimal | None = None
    chain_name: str | None = None
    offers_count: int = 0


@router.get("/catalog", response_model=list[CatalogProductResponse])
async def get_catalog_products(
    category: str | None = Query(None),
    brand: str | None = Query(None),
    q: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Browse the full product catalog with optional filters."""
    today = date.today()

    # Build subquery for best active offer per product
    best_offer_sq = (
        select(
            Offer.product_id,
            func.min(Offer.offer_price).label("best_price"),
            func.min(Offer.price_per_unit).label("best_ppu"),
        )
        .where(Offer.valid_from <= today, Offer.valid_to >= today)
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

    # Main query
    query = (
        select(
            Product,
            best_offer_sq.c.best_price,
            best_offer_sq.c.best_ppu,
            unit_ref_sq.c.unit_reference,
        )
        .outerjoin(best_offer_sq, Product.id == best_offer_sq.c.product_id)
        .outerjoin(unit_ref_sq, Product.id == unit_ref_sq.c.product_id)
    )

    if category:
        query = query.where(Product.category.ilike(category))
    if brand:
        query = query.where(Product.brand.ilike(f"%{brand}%"))
    if q:
        query = query.where(Product.name.ilike(f"%{q}%"))

    query = query.order_by(Product.name).offset(offset).limit(limit)

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
        )
        for row in rows
    ]


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
    offer_result = await db.execute(
        select(Offer)
        .options(joinedload(Offer.chain))
        .where(
            Offer.product_id == product_id,
            Offer.valid_from <= today,
            Offer.valid_to >= today,
        )
        .order_by(Offer.offer_price)
        .limit(1)
    )
    best = offer_result.unique().scalar_one_or_none()
    if not best:
        raise HTTPException(status_code=404, detail="No active offers found")

    return BestPriceResponse(
        product=ProductResponse.model_validate(product),
        best_price=best.offer_price,
        chain_name=best.chain.name if best.chain else "Unknown",
        valid_until=best.valid_to,
        original_price=best.original_price,
        discount_pct=best.discount_pct,
        price_per_unit=best.price_per_unit,
        unit_reference=best.unit_reference,
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

    trend_query = (
        select(
            func.to_char(
                func.date_trunc("month", Offer.valid_from), "YYYY-MM"
            ).label("period"),
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
        .group_by(func.date_trunc("month", Offer.valid_from))
        .order_by(func.date_trunc("month", Offer.valid_from))
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
