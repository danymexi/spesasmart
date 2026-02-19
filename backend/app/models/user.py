"""User-related models (profile, watchlist, stores)."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    push_token: Mapped[str | None] = mapped_column(Text)
    preferred_zone: Mapped[str] = mapped_column(
        String(100), default="Monza e Brianza"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    watchlist = relationship("UserWatchlist", back_populates="user", cascade="all, delete-orphan")
    stores = relationship("UserStore", back_populates="user", cascade="all, delete-orphan")


class UserWatchlist(Base):
    __tablename__ = "user_watchlist"
    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="uq_user_product"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_profiles.id")
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id")
    )
    target_price: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    notify_any_offer: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user = relationship("UserProfile", back_populates="watchlist")
    product = relationship("Product", back_populates="watchlist_entries")


class UserStore(Base):
    __tablename__ = "user_stores"
    __table_args__ = (
        UniqueConstraint("user_id", "store_id", name="uq_user_store"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_profiles.id")
    )
    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stores.id")
    )

    user = relationship("UserProfile", back_populates="stores")
    store = relationship("Store")
