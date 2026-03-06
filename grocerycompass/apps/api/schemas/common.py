from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginationMeta(BaseModel):
    page: int
    per_page: int
    total: int
    has_next: bool


class ResponseModel(BaseModel, Generic[T]):
    success: bool = True
    data: T | None = None
    meta: PaginationMeta | None = None
    timestamp: datetime = datetime.utcnow()


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = {}


class ErrorResponse(BaseModel):
    success: bool = False
    error: ErrorDetail
