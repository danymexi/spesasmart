"""Offer (price/promotion) model."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class Offer(Base):
    __tablename__ = "offers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id")
    )
    flyer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("flyers.id")
    )
    chain_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chains.id")
    )
    store_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stores.id"), nullable=True
    )
    original_price: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    offer_price: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    discount_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    discount_type: Mapped[str | None] = mapped_column(String(50))
    quantity: Mapped[str | None] = mapped_column(String(100))
    price_per_unit: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    unit_reference: Mapped[str | None] = mapped_column(String(20))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    raw_text: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    product = relationship("Product", back_populates="offers")
    flyer = relationship("Flyer", back_populates="offers")
    chain = relationship("Chain", back_populates="offers")
    store = relationship("Store", back_populates="offers")
