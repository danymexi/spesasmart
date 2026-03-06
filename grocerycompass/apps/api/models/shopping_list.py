import uuid
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, Integer, Numeric, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class ShoppingList(Base):
    __tablename__ = "shopping_lists"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="La mia lista")
    emoji: Mapped[str] = mapped_column(String(10), default="🛒")
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="shopping_lists")
    items = relationship("ListItem", back_populates="shopping_list", cascade="all, delete-orphan")


class ListItem(Base):
    __tablename__ = "list_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    list_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("shopping_lists.id", ondelete="CASCADE"))
    canonical_product_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("canonical_products.id"), nullable=True)
    free_text_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    quantity: Mapped[float] = mapped_column(Numeric(8, 3), nullable=False, default=1)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_checked: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    shopping_list = relationship("ShoppingList", back_populates="items")
    canonical_product = relationship("CanonicalProduct")
