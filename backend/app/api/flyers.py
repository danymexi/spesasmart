"""API routes for flyers."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models import Chain, Flyer, FlyerPage, Offer, Product

router = APIRouter(prefix="/flyers", tags=["flyers"])


class FlyerResponse(BaseModel):
    id: uuid.UUID
    chain_id: uuid.UUID
    store_id: uuid.UUID | None
    title: str | None
    valid_from: date
    valid_to: date
    source_url: str | None
    pages_count: int | None
    status: str
    created_at: datetime
    chain_name: str | None = None

    model_config = {"from_attributes": True}


class FlyerPageResponse(BaseModel):
    id: uuid.UUID
    page_number: int | None
    image_url: str | None
    processed: bool

    model_config = {"from_attributes": True}


class FlyerProductResponse(BaseModel):
    product_id: uuid.UUID
    product_name: str
    brand: str | None
    category: str | None
    original_price: Decimal | None
    offer_price: Decimal
    discount_pct: Decimal | None
    discount_type: str | None
    quantity: str | None

    model_config = {"from_attributes": True}


@router.get("", response_model=list[FlyerResponse])
async def list_flyers(
    chain: str | None = Query(None, description="Filter by chain slug"),
    active: bool = Query(True, description="Only show active flyers"),
    db: AsyncSession = Depends(get_db),
):
    query = select(Flyer).options(joinedload(Flyer.chain))

    if chain:
        query = query.join(Flyer.chain).where(Chain.slug == chain)
    if active:
        today = date.today()
        query = query.where(Flyer.valid_from <= today, Flyer.valid_to >= today)

    query = query.order_by(Flyer.valid_to.desc())
    result = await db.execute(query)
    flyers = result.unique().scalars().all()

    return [
        FlyerResponse(
            id=f.id,
            chain_id=f.chain_id,
            store_id=f.store_id,
            title=f.title,
            valid_from=f.valid_from,
            valid_to=f.valid_to,
            source_url=f.source_url,
            pages_count=f.pages_count,
            status=f.status,
            created_at=f.created_at,
            chain_name=f.chain.name if f.chain else None,
        )
        for f in flyers
    ]


@router.get("/{flyer_id}", response_model=FlyerResponse)
async def get_flyer(flyer_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Flyer).options(joinedload(Flyer.chain)).where(Flyer.id == flyer_id)
    )
    flyer = result.unique().scalar_one_or_none()
    if not flyer:
        raise HTTPException(status_code=404, detail="Flyer not found")
    return FlyerResponse(
        id=flyer.id,
        chain_id=flyer.chain_id,
        store_id=flyer.store_id,
        title=flyer.title,
        valid_from=flyer.valid_from,
        valid_to=flyer.valid_to,
        source_url=flyer.source_url,
        pages_count=flyer.pages_count,
        status=flyer.status,
        created_at=flyer.created_at,
        chain_name=flyer.chain.name if flyer.chain else None,
    )


@router.get("/{flyer_id}/pages", response_model=list[FlyerPageResponse])
async def get_flyer_pages(flyer_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(FlyerPage)
        .where(FlyerPage.flyer_id == flyer_id)
        .order_by(FlyerPage.page_number)
    )
    return result.scalars().all()


@router.get("/{flyer_id}/products", response_model=list[FlyerProductResponse])
async def get_flyer_products(
    flyer_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Offer)
        .options(joinedload(Offer.product))
        .where(Offer.flyer_id == flyer_id)
        .order_by(Offer.offer_price)
    )
    offers = result.unique().scalars().all()
    return [
        FlyerProductResponse(
            product_id=o.product_id,
            product_name=o.product.name,
            brand=o.product.brand,
            category=o.product.category,
            original_price=o.original_price,
            offer_price=o.offer_price,
            discount_pct=o.discount_pct,
            discount_type=o.discount_type,
            quantity=o.quantity,
        )
        for o in offers
    ]
