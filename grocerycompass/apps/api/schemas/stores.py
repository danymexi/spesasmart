import uuid
from datetime import datetime

from pydantic import BaseModel


class StoreResponse(BaseModel):
    id: uuid.UUID
    chain_id: uuid.UUID
    chain_name: str | None = None
    chain_slug: str | None = None
    chain_logo: str | None = None
    name: str | None
    address: str | None
    city: str | None
    province: str | None
    lat: float
    lng: float
    distance_km: float | None = None
    is_online_only: bool
    hours: dict | None = None

    model_config = {"from_attributes": True}


class NearbyStoresRequest(BaseModel):
    lat: float
    lng: float
    radius_km: int = 20
