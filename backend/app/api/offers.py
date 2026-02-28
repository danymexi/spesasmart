"""API routes for offers."""

import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
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
    previous_price: Decimal | None = None
    previous_date: date | None = None
    previous_chain: str | None = None

    model_config = {"from_attributes": True}


async def _get_previous_prices(
    product_ids: list[uuid.UUID],
    before_dates: dict[uuid.UUID, date],
    db: AsyncSession,
) -> dict[uuid.UUID, tuple[Decimal, date, str]]:
    """Batch-fetch the most recent expired offer for each product.

    Returns {product_id: (offer_price, valid_from, chain_name)}.
    Uses a window function to pick only the latest expired offer per product.
    """
    if not product_ids:
        return {}

    # Build a CTE: for each product, rank expired offers by valid_to DESC
    ranked = (
        select(
            Offer.product_id,
            Offer.offer_price,
            Offer.valid_from,
            Chain.name.label("chain_name"),
            func.row_number()
            .over(partition_by=Offer.product_id, order_by=Offer.valid_to.desc())
            .label("rn"),
        )
        .join(Chain, Offer.chain_id == Chain.id)
        .where(
            Offer.product_id.in_(product_ids),
            Offer.valid_to < date.today(),
        )
        .cte("ranked_prev")
    )

    query = select(
        ranked.c.product_id,
        ranked.c.offer_price,
        ranked.c.valid_from,
        ranked.c.chain_name,
    ).where(ranked.c.rn == 1)

    result = await db.execute(query)
    rows = result.all()

    return {
        row.product_id: (row.offer_price, row.valid_from, row.chain_name)
        for row in rows
    }


def _build_offer_responses(
    offers: list,
    previous: dict[uuid.UUID, tuple[Decimal, date, str]],
) -> list[OfferResponse]:
    """Build OfferResponse list enriched with previous-price data."""
    responses = []
    for o in offers:
        prev = previous.get(o.product_id)
        responses.append(
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
                previous_price=prev[0] if prev else None,
                previous_date=prev[1] if prev else None,
                previous_chain=prev[2] if prev else None,
            )
        )
    return responses


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

    product_ids = [o.product_id for o in offers]
    before_dates = {o.product_id: o.valid_from for o in offers if o.valid_from}
    previous = await _get_previous_prices(product_ids, before_dates, db)

    return _build_offer_responses(offers, previous)


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

    product_ids = [o.product_id for o in offers]
    before_dates = {o.product_id: o.valid_from for o in offers if o.valid_from}
    previous = await _get_previous_prices(product_ids, before_dates, db)

    return _build_offer_responses(offers, previous)
