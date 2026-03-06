import uuid
from datetime import datetime

from pydantic import BaseModel


class ListItemCreate(BaseModel):
    canonical_product_id: uuid.UUID | None = None
    free_text_name: str | None = None
    quantity: float = 1
    unit: str | None = None
    note: str | None = None


class ListItemUpdate(BaseModel):
    quantity: float | None = None
    unit: str | None = None
    is_checked: bool | None = None
    note: str | None = None
    sort_order: int | None = None


class ListItemResponse(BaseModel):
    id: uuid.UUID
    canonical_product_id: uuid.UUID | None
    free_text_name: str | None
    product_name: str | None = None
    product_brand: str | None = None
    product_image: str | None = None
    quantity: float
    unit: str | None
    is_checked: bool
    note: str | None
    sort_order: int
    added_at: datetime

    model_config = {"from_attributes": True}


class ShoppingListCreate(BaseModel):
    name: str = "La mia lista"
    emoji: str = "🛒"


class ShoppingListResponse(BaseModel):
    id: uuid.UUID
    name: str
    emoji: str
    is_archived: bool
    item_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
