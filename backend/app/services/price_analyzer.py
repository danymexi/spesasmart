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

PriceIndicator = Literal["top", "neutro", "flop"]

# Backward-compat mapping (old -> new)
_INDICATOR_COMPAT = {"ottimo": "top", "medio": "neutro", "alto": "flop"}


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
        offer_price: Optional[Decimal] = None,
        offer_ppu: Optional[Decimal] = None,
        session: AsyncSession | None = None,
    ) -> Optional[PriceIndicator]:
        """Classify a price as TOP / NEUTRO / FLOP.

        Uses both historical average AND cross-chain PPU comparison:
        - **top**: price < avg * 0.8, OR PPU <= min cross-chain PPU
        - **flop**: price > avg * 1.1, OR PPU > max cross-chain PPU
        - **neutro**: everything else

        Returns ``None`` when there is no active offer or no history.
        """
        close_session = False
        if session is None:
            session = async_session()
            close_session = True

        try:
            # Get current best offer if price not provided
            if offer_price is None:
                best_offer = await self.get_best_current_price(
                    product_id, session=session
                )
                if best_offer is None:
                    return None
                offer_price = best_offer.offer_price
                offer_ppu = best_offer.price_per_unit

            avg_price = await self.get_average_price(
                product_id, session=session
            )

            # Cross-chain PPU comparison
            min_ppu, max_ppu = await self._get_cross_chain_ppu_range(
                product_id, session=session
            )

            # Determine indicator
            is_top = False
            is_flop = False

            if avg_price and avg_price > 0:
                if offer_price < avg_price * Decimal("0.8"):
                    is_top = True
                elif offer_price > avg_price * Decimal("1.1"):
                    is_flop = True

            if offer_ppu and min_ppu and max_ppu:
                if offer_ppu <= min_ppu:
                    is_top = True
                elif offer_ppu > max_ppu and not is_top:
                    is_flop = True

            if is_top:
                indicator: PriceIndicator = "top"
            elif is_flop:
                indicator = "flop"
            else:
                indicator = "neutro"

            logger.debug(
                "Product %s: price=%s avg=%s ppu=%s min_ppu=%s max_ppu=%s -> %s",
                product_id, offer_price, avg_price, offer_ppu, min_ppu, max_ppu,
                indicator,
            )
            return indicator
        finally:
            if close_session:
                await session.close()

    async def _get_cross_chain_ppu_range(
        self,
        product_id: uuid.UUID,
        *,
        session: AsyncSession,
    ) -> tuple[Optional[Decimal], Optional[Decimal]]:
        """Return (min_ppu, max_ppu) across all active offers for a product."""
        active_clauses = self._active_offer_filter()
        stmt = select(
            func.min(Offer.price_per_unit),
            func.max(Offer.price_per_unit),
        ).where(
            Offer.product_id == product_id,
            Offer.price_per_unit.isnot(None),
            *active_clauses,
        )
        result = await session.execute(stmt)
        row = result.one_or_none()
        if row:
            return row[0], row[1]
        return None, None

    async def compute_indicators_batch(
        self,
        product_ids: list[uuid.UUID],
        *,
        session: AsyncSession,
    ) -> dict[uuid.UUID, PriceIndicator]:
        """Compute indicators for multiple products in a single pass.

        Returns a mapping of product_id -> indicator.
        """
        if not product_ids:
            return {}

        today = date.today()

        # Batch fetch: avg prices
        avg_stmt = (
            select(Offer.product_id, func.avg(Offer.offer_price))
            .where(Offer.product_id.in_(product_ids))
            .group_by(Offer.product_id)
        )
        avg_result = await session.execute(avg_stmt)
        avg_map = {pid: Decimal(str(round(avg, 2))) for pid, avg in avg_result.all() if avg}

        # Batch fetch: best active price + PPU per product
        best_stmt = (
            select(
                Offer.product_id,
                func.min(Offer.offer_price),
                func.min(Offer.price_per_unit),
                func.max(Offer.price_per_unit),
            )
            .where(
                Offer.product_id.in_(product_ids),
                Offer.valid_from <= today,
                Offer.valid_to >= today,
            )
            .group_by(Offer.product_id)
        )
        best_result = await session.execute(best_stmt)
        best_map = {}
        ppu_range_map = {}
        for pid, best_price, min_ppu, max_ppu in best_result.all():
            best_map[pid] = best_price
            ppu_range_map[pid] = (min_ppu, max_ppu)

        indicators: dict[uuid.UUID, PriceIndicator] = {}
        for pid in product_ids:
            best_price = best_map.get(pid)
            if best_price is None:
                continue

            avg_price = avg_map.get(pid)
            min_ppu, max_ppu = ppu_range_map.get(pid, (None, None))
            # For batch, use min_ppu as the offer's PPU (best price = best PPU assumption)
            offer_ppu = min_ppu

            is_top = False
            is_flop = False

            if avg_price and avg_price > 0:
                if best_price < avg_price * Decimal("0.8"):
                    is_top = True
                elif best_price > avg_price * Decimal("1.1"):
                    is_flop = True

            if offer_ppu and min_ppu and max_ppu and min_ppu != max_ppu:
                if offer_ppu <= min_ppu:
                    is_top = True
                elif offer_ppu >= max_ppu and not is_top:
                    is_flop = True

            if is_top:
                indicators[pid] = "top"
            elif is_flop:
                indicators[pid] = "flop"
            else:
                indicators[pid] = "neutro"

        return indicators

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
