import uuid

from pydantic import BaseModel


class CompareRequest(BaseModel):
    lat: float
    lng: float
    radius_km: int = 20
    max_stores: int = 2
    travel_cost_per_extra: float = 0.0


class StoreBreakdownItem(BaseModel):
    item_name: str
    quantity: float
    price: float
    total: float
    is_discounted: bool


class SingleStoreResult(BaseModel):
    store_id: uuid.UUID
    store_name: str
    chain_slug: str
    chain_name: str
    total: float
    coverage_pct: float
    missing_count: int
    distance_km: float | None


class MultiStoreAssignment(BaseModel):
    store_id: uuid.UUID
    store_name: str
    chain_slug: str
    items: list[StoreBreakdownItem]
    subtotal: float


class MultiStoreResult(BaseModel):
    stores: list[MultiStoreAssignment]
    total: float
    travel_cost: float
    savings_vs_best_single: float


class CompareResponse(BaseModel):
    list_id: uuid.UUID
    single_store_ranking: list[SingleStoreResult]
    multi_store_optimal: MultiStoreResult | None
