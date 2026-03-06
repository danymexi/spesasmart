import uuid
from datetime import datetime

from geoalchemy2 import Geography
from sqlalchemy import String, Boolean, DateTime, Numeric, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Store(Base):
    __tablename__ = "stores"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chain_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chains.id"))
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    address: Mapped[str | None] = mapped_column(String, nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    province: Mapped[str | None] = mapped_column(String(2), nullable=True)
    lat: Mapped[float] = mapped_column(Numeric(10, 8), nullable=False)
    lng: Mapped[float] = mapped_column(Numeric(11, 8), nullable=False)
    geom = mapped_column(Geography("POINT", srid=4326), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    hours: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_online_only: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_verified: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    chain = relationship("Chain", back_populates="stores")
