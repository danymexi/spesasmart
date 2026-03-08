"""Store (point of sale) model."""

import uuid

from sqlalchemy import BigInteger, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Store(Base):
    __tablename__ = "stores"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    chain_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chains.id")
    )
    name: Mapped[str | None] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(100))
    province: Mapped[str] = mapped_column(String(10), default="MB")
    zip_code: Mapped[str | None] = mapped_column(String(10))
    lat: Mapped[float | None] = mapped_column(Numeric(10, 7))
    lon: Mapped[float | None] = mapped_column(Numeric(10, 7))
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    opening_hours: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    website_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    osm_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)

    chain = relationship("Chain", back_populates="stores")
    flyers = relationship("Flyer", back_populates="store")
    offers = relationship("Offer", back_populates="store")
