"""Price analysis service.

Provides historical price tracking, best-offer detection and a traffic-light
price indicator (ottimo / medio / alto) for the SpesaSmart frontend.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import async_session
from app.models import Chain, Offer, Product

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data transfer objects
# ---------------------------------------------------------------------------

PriceIndicator = Literal["ottimo", "medio", "alto"]


@dataclass(frozen=True, slots=True)
class PricePoint:
    """A single price observation over time."""

    offer_id: uuid.UUID
    chain_name: str
    price: Decimal
    original_price: Optional[Decimal]
    discount_pct: Optional[Decimal]
    valid_from: Optional[date]
    valid_to: Optional[date]
    recorded_at: datetime


@dataclass(frozen=True, slots=True)
class ChainComparison:
    """Price comparison for a single chain."""

    chain_id: uuid.UUID
    chain_name: str
    current_price: Decimal
    original_price: Optional[Decimal]
    discount_pct: Optional[Decimal]
    valid_to: Optional[date]


@dataclass(frozen=True, slots=True)
class CategoryOffer:
    """An offer for use in category-level rankings."""

    offer_id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    brand: Optional[str]
    chain_name: str
    price: Decimal
    original_price: Optional[Decimal]
    discount_pct: Optional[Decimal]
    valid_to: Optional[date]


class PriceAnalyzer:
    """Async service for price history and comparisons."""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _active_offer_filter():
        """SQLAlchemy clause that limits to currently valid offers."""
        today = date.today()
        return (
            (Offer.valid_from <= today) | (Offer.valid_from.is_(None)),
            (Offer.valid_to >= today) | (Offer.valid_to.is_(None)),
        )

    # ------------------------------------------------------------------
    # Price history
    # ------------------------------------------------------------------

    async def get_price_history(
        self,
        product_id: uuid.UUID,
        *,
        session: AsyncSession | None = None,
    ) -> list[PricePoint]:
        """Return all known price observations for *product_id*, sorted by
        date descending (newest first)."""
        close_session = False
        if session is None:
            session = async_session()
            close_session = True

        try:
            stmt = (
                select(Offer, Chain.name)
                .join(Chain, Offer.chain_id == Chain.id)
                .where(Offer.product_id == product_id)
                .order_by(Offer.created_at.desc())
            )
            result = await session.execute(stmt)
            rows = result.all()

            return [
                PricePoint(
                    offer_id=offer.id,
                    chain_name=chain_name,
                    price=offer.offer_price,
                    original_price=offer.original_price,
                    discount_pct=offer.discount_pct,
                    valid_from=offer.valid_from,
                    valid_to=offer.valid_to,
                    recorded_at=offer.created_at,
                )
                for offer, chain_name in rows
            ]
        finally:
            if close_session:
                await session.close()

    # ------------------------------------------------------------------
    # Average price
    # ------------------------------------------------------------------

    async def get_average_price(
        self,
        product_id: uuid.UUID,
        *,
        session: AsyncSession | None = None,
    ) -> Optional[Decimal]:
        """Compute the simple average of all historical offer prices.

        Returns ``None`` if no offers exist for the product.
        """
        close_session = False
        if session is None:
            session = async_session()
            close_session = True

        try:
            stmt = select(func.avg(Offer.offer_price)).where(
                Offer.product_id == product_id
            )
            result = await session.execute(stmt)
            avg = result.scalar_one_or_none()

            if avg is None:
                return None
            return Decimal(str(round(avg, 2)))
        finally:
            if close_session:
                await session.close()

    # ------------------------------------------------------------------
    # Best current price
    # ------------------------------------------------------------------

    async def get_best_current_price(
        self,
        product_id: uuid.UUID,
        *,
        session: AsyncSession | None = None,
    ) -> Optional[Offer]:
        """Return the active :class:`Offer` with the lowest price.

        Only offers that are valid *today* are considered.  Returns ``None``
        when there are no active offers.
        """
        close_session = False
        if session is None:
            session = async_session()
            close_session = True

        try:
            active_clauses = self._active_offer_filter()
            stmt = (
                select(Offer)
                .options(joinedload(Offer.chain))
                .where(Offer.product_id == product_id, *active_clauses)
                .order_by(Offer.offer_price.asc())
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
        finally:
            if close_session:
                await session.close()

    # ------------------------------------------------------------------
    # Price indicator (traffic-light)
    # ------------------------------------------------------------------

    async def get_price_indicator(
        self,
        product_id: uuid.UUID,
        *,
        session: AsyncSession | None = None,
    ) -> Optional[PriceIndicator]:
        """Classify the current best price relative to the historical average.

        Rules:
        - **ottimo** (green): price < average * 0.8
        - **medio**  (yellow): average * 0.8 <= price <= average * 1.1
        - **alto**   (red):   price > average * 1.1

        Returns ``None`` when there is no active offer or no history.
        """
        close_session = False
        if session is None:
            session = async_session()
            close_session = True

        try:
            best_offer = await self.get_best_current_price(
                product_id, session=session
            )
            if best_offer is None:
                return None

            avg_price = await self.get_average_price(
                product_id, session=session
            )
            if avg_price is None or avg_price == 0:
                return None

            current_price = best_offer.offer_price

            threshold_green = avg_price * Decimal("0.8")
            threshold_red = avg_price * Decimal("1.1")

            if current_price < threshold_green:
                indicator: PriceIndicator = "ottimo"
            elif current_price > threshold_red:
                indicator = "alto"
            else:
                indicator = "medio"

            logger.debug(
                "Product %s: price=%s avg=%s -> %s",
                product_id,
                current_price,
                avg_price,
                indicator,
            )
            return indicator
        finally:
            if close_session:
                await session.close()

    # ------------------------------------------------------------------
    # Best offers by category
    # ------------------------------------------------------------------

    async def get_best_offers_by_category(
        self,
        category: str,
        *,
        limit: int = 50,
        session: AsyncSession | None = None,
    ) -> list[CategoryOffer]:
        """Return active offers for a category, sorted by price ascending."""
        close_session = False
        if session is None:
            session = async_session()
            close_session = True

        try:
            active_clauses = self._active_offer_filter()
            stmt = (
                select(Offer, Product, Chain.name)
                .join(Product, Offer.product_id == Product.id)
                .join(Chain, Offer.chain_id == Chain.id)
                .where(Product.category == category, *active_clauses)
                .order_by(Offer.offer_price.asc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            rows = result.all()

            return [
                CategoryOffer(
                    offer_id=offer.id,
                    product_id=product.id,
                    product_name=product.name,
                    brand=product.brand,
                    chain_name=chain_name,
                    price=offer.offer_price,
                    original_price=offer.original_price,
                    discount_pct=offer.discount_pct,
                    valid_to=offer.valid_to,
                )
                for offer, product, chain_name in rows
            ]
        finally:
            if close_session:
                await session.close()

    # ------------------------------------------------------------------
    # Chain comparison
    # ------------------------------------------------------------------

    async def compare_chains(
        self,
        product_id: uuid.UUID,
        *,
        session: AsyncSession | None = None,
    ) -> list[ChainComparison]:
        """Compare the current price of a product across all chains.

        For each chain that has an active offer, the cheapest one is returned.
        Results are sorted by price ascending (cheapest first).
        """
        close_session = False
        if session is None:
            session = async_session()
            close_session = True

        try:
            active_clauses = self._active_offer_filter()
            stmt = (
                select(Offer, Chain)
                .join(Chain, Offer.chain_id == Chain.id)
                .where(Offer.product_id == product_id, *active_clauses)
                .order_by(Chain.id, Offer.offer_price.asc())
            )
            result = await session.execute(stmt)
            rows = result.all()

            # Keep only the cheapest offer per chain
            seen_chains: set[uuid.UUID] = set()
            comparisons: list[ChainComparison] = []

            for offer, chain in rows:
                if chain.id in seen_chains:
                    continue
                seen_chains.add(chain.id)
                comparisons.append(
                    ChainComparison(
                        chain_id=chain.id,
                        chain_name=chain.name,
                        current_price=offer.offer_price,
                        original_price=offer.original_price,
                        discount_pct=offer.discount_pct,
                        valid_to=offer.valid_to,
                    )
                )

            # Sort by price ascending
            comparisons.sort(key=lambda c: c.current_price)

            logger.debug(
                "Product %s: found prices at %d chains",
                product_id,
                len(comparisons),
            )
            return comparisons
        finally:
            if close_session:
                await session.close()
