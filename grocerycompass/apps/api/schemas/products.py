import uuid
from datetime import datetime

from pydantic import BaseModel


class StorePriceResponse(BaseModel):
    store_id: uuid.UUID
    store_name: str
    chain_slug: str
    chain_name: str
    chain_logo: str | None
    price: float
    price_discounted: float | None
    discount_label: str | None
    price_per_unit: float | None
    unit_label: str | None
    in_stock: bool
    distance_km: float | None = None
    last_scraped: datetime

    model_config = {"from_attributes": True}


class ProductResponse(BaseModel):
    id: uuid.UUID
    name: str
    brand: str | None
    category_name: str | None = None
    quantity_value: float | None
    quantity_unit: str | None
    quantity_raw: str | None
    barcode_ean: str | None
    image_url: str | None
    description: str | None
    tags: list[str] | None
    min_price: float | None = None
    num_chains: int | None = None
    prices: list[StorePriceResponse] = []

    model_config = {"from_attributes": True}


class ProductSearchResponse(BaseModel):
    products: list[ProductResponse]
    total: int
    page: int
    per_page: int
    has_next: bool


class PriceHistoryEntry(BaseModel):
    date: str
    price: float
    chain_slug: str


class PriceHistoryResponse(BaseModel):
    product_id: uuid.UUID
    entries: list[PriceHistoryEntry]
