import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, Numeric, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class ComparisonResult(Base):
    __tablename__ = "comparison_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    list_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("shopping_lists.id", ondelete="CASCADE"))
    user_lat: Mapped[float | None] = mapped_column(Numeric(10, 8), nullable=True)
    user_lng: Mapped[float | None] = mapped_column(Numeric(11, 8), nullable=True)
    radius_km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
