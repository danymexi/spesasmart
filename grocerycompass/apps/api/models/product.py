import uuid
from datetime import datetime, date

from sqlalchemy import String, Boolean, DateTime, Numeric, Integer, ForeignKey, func, ARRAY
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class CanonicalProduct(Base):
    __tablename__ = "canonical_products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(150), nullable=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True)
    quantity_value: Mapped[float | None] = mapped_column(Numeric(10, 3), nullable=True)
    quantity_unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    quantity_raw: Mapped[str | None] = mapped_column(String(100), nullable=True)
    barcode_ean: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    image_url: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    match_confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    category = relationship("Category", back_populates="products")
    store_products = relationship("StoreProduct", back_populates="canonical_product")


class StoreProduct(Base):
    __tablename__ = "store_products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_product_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("canonical_products.id"), nullable=True)
    store_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("stores.id"), nullable=True)
    chain_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chains.id"))
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    name_original: Mapped[str | None] = mapped_column(String(300), nullable=True)
    price: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    price_discounted: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    discount_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    discount_ends_at: Mapped[date | None] = mapped_column(nullable=True)
    price_per_unit: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    unit_label: Mapped[str | None] = mapped_column(String(50), nullable=True)
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True)
    product_url: Mapped[str | None] = mapped_column(String, nullable=True)
    last_scraped: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scrape_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    canonical_product = relationship("CanonicalProduct", back_populates="store_products")
    chain = relationship("Chain", back_populates="store_products")
