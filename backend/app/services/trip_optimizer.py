"""Trip optimizer service.

Analyses a user's shopping list and finds optimal purchasing strategies:
- **Single store**: best chain to buy everything at one place.
- **Multi store**: cherry-pick the cheapest chain per item for maximum savings.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import Chain, Offer, Product, ShoppingListItem

logger = logging.getLogger(__name__)


@dataclass
class TripItem:
    product_name: str
    offer_price: Decimal
    chain_name: str


@dataclass
class StoreTrip:
    chain_name: str
    items: list[TripItem] = field(default_factory=list)
    total: Decimal = Decimal("0")


@dataclass
class TripOptimizationResult:
    single_store_best: StoreTrip | None
    multi_store_plan: list[StoreTrip]
    single_store_total: Decimal
    multi_store_total: Decimal
    potential_savings: Decimal


class TripOptimizer:
    """Compute optimal shopping trip strategies from a user's list."""

    async def optimize(
        self,
        user_id: uuid.UUID,
        session: AsyncSession,
    ) -> TripOptimizationResult:
        """Analyse the user's shopping list and return optimisation results."""
        today = date.today()

        # 1. Fetch shopping list items with linked products
        sl_result = await session.execute(
            select(ShoppingListItem)
            .options(joinedload(ShoppingListItem.product))
            .where(
                ShoppingListItem.user_id == user_id,
                ShoppingListItem.checked.is_(False),
            )
        )
        items = sl_result.unique().scalars().all()

        # Filter to items with linked products
        product_items = [i for i in items if i.product_id is not None]

        if not product_items:
            return TripOptimizationResult(
                single_store_best=None,
                multi_store_plan=[],
                single_store_total=Decimal("0"),
                multi_store_total=Decimal("0"),
                potential_savings=Decimal("0"),
            )

        product_ids = [i.product_id for i in product_items]

        # 2. Fetch all active offers for these products
        offers_result = await session.execute(
            select(Offer)
            .options(joinedload(Offer.chain))
            .where(
                Offer.product_id.in_(product_ids),
                Offer.valid_from <= today,
                Offer.valid_to >= today,
            )
            .order_by(Offer.offer_price)
        )
        all_offers = offers_result.unique().scalars().all()

        # 3. Build price matrix: product_id -> {chain_name -> best_price}
        from collections import defaultdict

        price_matrix: dict[uuid.UUID, dict[str, tuple[Decimal, str]]] = defaultdict(dict)
        for offer in all_offers:
            chain_name = offer.chain.name if offer.chain else "Unknown"
            pid = offer.product_id
            if chain_name not in price_matrix[pid]:
                price_matrix[pid][chain_name] = (offer.offer_price, chain_name)

        # Product name lookup
        product_names: dict[uuid.UUID, str] = {}
        for item in product_items:
            product_names[item.product_id] = (
                item.product.name if item.product else item.custom_name or "Unknown"
            )

        # Get all unique chains
        all_chains: set[str] = set()
        for chain_prices in price_matrix.values():
            all_chains.update(chain_prices.keys())

        # 4. Single-store strategy: for each chain, sum what's available
        single_store_results: list[StoreTrip] = []
        for chain_name in sorted(all_chains):
            trip = StoreTrip(chain_name=chain_name)
            for item in product_items:
                pid = item.product_id
                if chain_name in price_matrix.get(pid, {}):
                    price, _ = price_matrix[pid][chain_name]
                    item_total = price * item.quantity
                    trip.items.append(TripItem(
                        product_name=product_names.get(pid, "Unknown"),
                        offer_price=item_total,
                        chain_name=chain_name,
                    ))
                    trip.total += item_total
            if trip.items:
                single_store_results.append(trip)

        # Best single store (most items covered, then cheapest)
        single_store_results.sort(key=lambda t: (-len(t.items), t.total))
        single_store_best = single_store_results[0] if single_store_results else None

        # 5. Multi-store strategy: for each product, pick the cheapest chain
        multi_store_map: dict[str, StoreTrip] = {}
        multi_total = Decimal("0")

        for item in product_items:
            pid = item.product_id
            chain_prices = price_matrix.get(pid, {})
            if not chain_prices:
                continue

            # Find cheapest
            best_chain, (best_price, _) = min(
                chain_prices.items(), key=lambda x: x[1][0]
            )
            item_total = best_price * item.quantity

            if best_chain not in multi_store_map:
                multi_store_map[best_chain] = StoreTrip(chain_name=best_chain)
            multi_store_map[best_chain].items.append(TripItem(
                product_name=product_names.get(pid, "Unknown"),
                offer_price=item_total,
                chain_name=best_chain,
            ))
            multi_store_map[best_chain].total += item_total
            multi_total += item_total

        multi_store_plan = sorted(multi_store_map.values(), key=lambda t: t.chain_name)

        single_total = single_store_best.total if single_store_best else Decimal("0")
        savings = single_total - multi_total if single_total > multi_total else Decimal("0")

        return TripOptimizationResult(
            single_store_best=single_store_best,
            multi_store_plan=multi_store_plan,
            single_store_total=single_total,
            multi_store_total=multi_total,
            potential_savings=savings,
        )
