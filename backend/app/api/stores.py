"""API routes for stores."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models import Store

router = APIRouter(prefix="/stores", tags=["stores"])


class StoreResponse(BaseModel):
    id: uuid.UUID
    chain_id: uuid.UUID
    name: str | None
    address: str | None
    city: str | None
    province: str
    zip_code: str | None
    lat: float | None
    lon: float | None
    chain_name: str | None = None

    model_config = {"from_attributes": True}


@router.get("", response_model=list[StoreResponse])
async def list_stores(
    city: str | None = Query(None, description="Filter by city"),
    chain: str | None = Query(None, description="Filter by chain slug"),
    db: AsyncSession = Depends(get_db),
):
    query = select(Store).options(joinedload(Store.chain))
    if city:
        query = query.where(Store.city.ilike(f"%{city}%"))
    if chain:
        query = query.join(Store.chain).where(Store.chain.has(slug=chain))
    result = await db.execute(query)
    stores = result.unique().scalars().all()
    return [
        StoreResponse(
            id=s.id,
            chain_id=s.chain_id,
            name=s.name,
            address=s.address,
            city=s.city,
            province=s.province,
            zip_code=s.zip_code,
            lat=float(s.lat) if s.lat else None,
            lon=float(s.lon) if s.lon else None,
            chain_name=s.chain.name if s.chain else None,
        )
        for s in stores
    ]


@router.get("/{store_id}", response_model=StoreResponse)
async def get_store(store_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Store).options(joinedload(Store.chain)).where(Store.id == store_id)
    )
    store = result.unique().scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    return StoreResponse(
        id=store.id,
        chain_id=store.chain_id,
        name=store.name,
        address=store.address,
        city=store.city,
        province=store.province,
        zip_code=store.zip_code,
        lat=float(store.lat) if store.lat else None,
        lon=float(store.lon) if store.lon else None,
        chain_name=store.chain.name if store.chain else None,
    )
