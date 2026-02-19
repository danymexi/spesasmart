"""API routes for products."""

import uuid
from datetime import date
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


class PriceHistoryPoint(BaseModel):
    date: date
    price: Decimal
    chain_name: str
    discount_type: str | None


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


class ProductSearchResult(BaseModel):
    product: ProductResponse
    best_current_price: Decimal | None = None
    chain_name: str | None = None
    offers_count: int = 0


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
    )
