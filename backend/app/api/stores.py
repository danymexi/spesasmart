"""API routes for stores."""

import math
import uuid
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models import Store

router = APIRouter(prefix="/stores", tags=["stores"])


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in km between two lat/lon points using Haversine."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


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
    phone: str | None = None
    opening_hours: dict | None = None
    website_url: str | None = None
    chain_name: str | None = None

    model_config = {"from_attributes": True}


class NearbyChainInfo(BaseModel):
    chain_name: str
    chain_slug: str
    store_count: int
    min_distance_km: float


class NearbyStoresResponse(BaseModel):
    chains: list[NearbyChainInfo]
    chain_slugs: list[str]
    total_stores: int


@router.get("/nearby", response_model=NearbyStoresResponse)
async def get_nearby_stores(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(default=20, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Find stores within radius, grouped by chain."""
    result = await db.execute(
        select(Store).options(joinedload(Store.chain)).where(
            Store.lat.isnot(None), Store.lon.isnot(None)
        )
    )
    stores = result.unique().scalars().all()

    chain_stores: dict[str, list[tuple[float, "Store"]]] = defaultdict(list)
    for s in stores:
        dist = _haversine_km(lat, lon, float(s.lat), float(s.lon))
        if dist <= radius_km and s.chain:
            chain_stores[s.chain.slug].append((dist, s))

    chains = []
    for slug, store_list in sorted(chain_stores.items()):
        store_list.sort(key=lambda x: x[0])
        chain_name = store_list[0][1].chain.name
        chains.append(NearbyChainInfo(
            chain_name=chain_name,
            chain_slug=slug,
            store_count=len(store_list),
            min_distance_km=round(store_list[0][0], 1),
        ))

    chains.sort(key=lambda c: c.min_distance_km)

    return NearbyStoresResponse(
        chains=chains,
        chain_slugs=[c.chain_slug for c in chains],
        total_stores=sum(c.store_count for c in chains),
    )


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
            phone=s.phone,
            opening_hours=s.opening_hours,
            website_url=s.website_url,
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
        phone=store.phone,
        opening_hours=store.opening_hours,
        website_url=store.website_url,
        chain_name=store.chain.name if store.chain else None,
    )
