import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from geoalchemy2.functions import ST_DWithin, ST_Distance, ST_Point, ST_GeogFromText
from sqlalchemy import select, cast, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.store import Store
from models.chain import Chain
from schemas.stores import StoreResponse
from schemas.common import ResponseModel

router = APIRouter()


@router.get("", response_model=ResponseModel[list[StoreResponse]])
async def get_nearby_stores(
    lat: float = Query(...),
    lng: float = Query(...),
    radius: int = Query(20, description="Raggio in km"),
    db: AsyncSession = Depends(get_db),
):
    radius_meters = radius * 1000
    point = func.ST_Point(lng, lat, type_=None)
    geog_point = func.ST_SetSRID(point, 4326)

    query = (
        select(
            Store,
            Chain,
            func.ST_Distance(
                Store.geom,
                func.ST_GeogFromText(f"POINT({lng} {lat})")
            ).label("distance_m"),
        )
        .join(Chain, Store.chain_id == Chain.id)
        .where(Store.is_active == True)
        .where(
            func.ST_DWithin(
                Store.geom,
                func.ST_GeogFromText(f"POINT({lng} {lat})"),
                radius_meters,
            )
        )
        .order_by(text("distance_m"))
    )

    result = await db.execute(query)
    stores = []
    for store, chain, distance_m in result.all():
        stores.append(StoreResponse(
            id=store.id,
            chain_id=store.chain_id,
            chain_name=chain.name,
            chain_slug=chain.slug,
            chain_logo=chain.logo_url,
            name=store.name,
            address=store.address,
            city=store.city,
            province=store.province,
            lat=float(store.lat),
            lng=float(store.lng),
            distance_km=round(distance_m / 1000, 1) if distance_m else None,
            is_online_only=store.is_online_only,
            hours=store.hours,
        ))

    return ResponseModel(data=stores)


@router.get("/{store_id}", response_model=ResponseModel[StoreResponse])
async def get_store(store_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Store, Chain)
        .join(Chain, Store.chain_id == Chain.id)
        .where(Store.id == store_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Negozio non trovato")

    store, chain = row
    return ResponseModel(data=StoreResponse(
        id=store.id,
        chain_id=store.chain_id,
        chain_name=chain.name,
        chain_slug=chain.slug,
        chain_logo=chain.logo_url,
        name=store.name,
        address=store.address,
        city=store.city,
        province=store.province,
        lat=float(store.lat),
        lng=float(store.lng),
        is_online_only=store.is_online_only,
        hours=store.hours,
    ))
