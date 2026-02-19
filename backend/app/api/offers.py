"""API routes for offers."""

import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models import Chain, Offer, Product

router = APIRouter(prefix="/offers", tags=["offers"])


class OfferResponse(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    brand: str | None
    category: str | None
    chain_id: uuid.UUID
    chain_name: str
    original_price: Decimal | None
    offer_price: Decimal
    discount_pct: Decimal | None
    discount_type: str | None
    quantity: str | None
    price_per_unit: Decimal | None
    valid_from: date | None
    valid_to: date | None
    image_url: str | None = None

    model_config = {"from_attributes": True}


@router.get("/active", response_model=list[OfferResponse])
async def get_active_offers(
    chain: str | None = Query(None, description="Comma-separated chain slugs"),
    category: str | None = Query(None),
    min_discount: float | None = Query(None, description="Minimum discount %"),
    sort: str = Query("price", enum=["price", "discount", "name"]),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
):
    today = date.today()
    query = (
        select(Offer)
        .options(joinedload(Offer.product), joinedload(Offer.chain))
        .where(Offer.valid_from <= today, Offer.valid_to >= today)
    )

    if chain:
        slugs = [s.strip() for s in chain.split(",")]
        query = query.join(Offer.chain).where(Chain.slug.in_(slugs))

    if category:
        query = query.join(Offer.product).where(
            Product.category.ilike(f"%{category}%")
        )

    if min_discount:
        query = query.where(Offer.discount_pct >= min_discount)

    if sort == "price":
        query = query.order_by(Offer.offer_price)
    elif sort == "discount":
        query = query.order_by(Offer.discount_pct.desc().nulls_last())
    else:
        query = query.order_by(Product.name)

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    offers = result.unique().scalars().all()

    return [
        OfferResponse(
            id=o.id,
            product_id=o.product_id,
            product_name=o.product.name if o.product else "Unknown",
            brand=o.product.brand if o.product else None,
            category=o.product.category if o.product else None,
            chain_id=o.chain_id,
            chain_name=o.chain.name if o.chain else "Unknown",
            original_price=o.original_price,
            offer_price=o.offer_price,
            discount_pct=o.discount_pct,
            discount_type=o.discount_type,
            quantity=o.quantity,
            price_per_unit=o.price_per_unit,
            valid_from=o.valid_from,
            valid_to=o.valid_to,
            image_url=o.product.image_url if o.product else None,
        )
        for o in offers
    ]


@router.get("/best", response_model=list[OfferResponse])
async def get_best_offers(
    category: str | None = Query(None),
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Best offers sorted by discount percentage."""
    today = date.today()
    query = (
        select(Offer)
        .options(joinedload(Offer.product), joinedload(Offer.chain))
        .where(
            Offer.valid_from <= today,
            Offer.valid_to >= today,
            Offer.discount_pct.is_not(None),
        )
    )

    if category:
        query = query.join(Offer.product).where(
            Product.category.ilike(f"%{category}%")
        )

    query = query.order_by(Offer.discount_pct.desc()).limit(limit)
    result = await db.execute(query)
    offers = result.unique().scalars().all()

    return [
        OfferResponse(
            id=o.id,
            product_id=o.product_id,
            product_name=o.product.name if o.product else "Unknown",
            brand=o.product.brand if o.product else None,
            category=o.product.category if o.product else None,
            chain_id=o.chain_id,
            chain_name=o.chain.name if o.chain else "Unknown",
            original_price=o.original_price,
            offer_price=o.offer_price,
            discount_pct=o.discount_pct,
            discount_type=o.discount_type,
            quantity=o.quantity,
            price_per_unit=o.price_per_unit,
            valid_from=o.valid_from,
            valid_to=o.valid_to,
            image_url=o.product.image_url if o.product else None,
        )
        for o in offers
    ]
