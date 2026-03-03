"""Trip optimizer service.

Analyses a user's shopping list and finds optimal purchasing strategies:
- **Single store**: best chain to buy everything at one place.
- **Multi store**: cherry-pick the cheapest chain per item for maximum savings.

Custom-name items (free-text entries without a product_id) are resolved
on-the-fly via fuzzy matching against the product catalogue, picking the
cheapest matching offer per chain.
"""

import logging
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from difflib import SequenceMatcher

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import Chain, Offer, Product, ShoppingListItem

logger = logging.getLogger(__name__)

# Common Italian filler words to skip when extracting search keywords
_FILLER_WORDS = frozenset({
    "alla", "allo", "alle", "al", "ai", "della", "dello", "delle", "del",
    "dei", "con", "per", "senza", "bio", "gli", "dei", "una", "uno", "il",
    "la", "lo", "le", "di", "da", "in",
})


def _normalize_product_name(name: str) -> str:
    """Normalize a product name for fuzzy grouping (copied from products.py)."""
    n = name.lower().strip()
    n = re.sub(r"\b\d+\s*(pz|pezzi|rotoli|rotoloni|x|ml|cl|l|g|kg|gr)\b", "", n)
    n = re.sub(r"\bx\s*\d+\b", "", n)
    n = re.sub(r"\bcarta\s+(igienica|cucina|assorbente)\b", "", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _names_match(norm_a: str, norm_b: str, threshold: float = 0.78) -> bool:
    """Check if two normalized names refer to the same product."""
    shorter, longer = sorted([norm_a, norm_b], key=len)

    if len(shorter) >= 6 and shorter in longer:
        pos = longer.find(shorter)
        if pos == 0 or len(shorter) / len(longer) >= 0.4:
            return True

    words_a = norm_a.split()
    words_b = norm_b.split()
    if len(words_a) >= 2 and len(words_b) >= 2:
        common_prefix = 0
        for wa, wb in zip(words_a, words_b):
            if wa == wb:
                common_prefix += 1
            else:
                break
        if common_prefix >= 2:
            return True

    ratio = SequenceMatcher(None, norm_a, norm_b).ratio()
    return ratio >= threshold


@dataclass
class TripItem:
    product_name: str
    offer_price: Decimal
    chain_name: str
    search_term: str | None = None


@dataclass
class StoreTrip:
    chain_name: str
    items: list[TripItem] = field(default_factory=list)
    total: Decimal = Decimal("0")
    items_covered: int = 0


@dataclass
class TripOptimizationResult:
    single_store_best: StoreTrip | None
    multi_store_plan: list[StoreTrip]
    single_store_total: Decimal
    multi_store_total: Decimal
    potential_savings: Decimal
    all_single_stores: list[StoreTrip] = field(default_factory=list)
    items_total: int = 0
    items_not_covered: int = 0


class TripOptimizer:
    """Compute optimal shopping trip strategies from a user's list."""

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        """Extract significant keywords (>= 4 chars) from free text."""
        words = text.lower().split()
        keywords = [w for w in words if len(w) >= 4 and w not in _FILLER_WORDS]
        return keywords if keywords else words[:1]

    async def _resolve_custom_items(
        self,
        custom_items: list[ShoppingListItem],
        session: AsyncSession,
        today: date,
    ) -> tuple[
        dict[uuid.UUID, dict[str, tuple[Decimal, str, str]]],  # item_id -> {chain -> (price, chain, product_name)}
        dict[uuid.UUID, str],  # item_id -> display label (custom_name)
    ]:
        """Resolve custom_name items to cheapest matching offers per chain.

        Returns:
            price_matrix: item_id -> {chain_name -> (price, chain_name, matched_product_name)}
            labels: item_id -> original custom_name for display
        """
        price_matrix: dict[uuid.UUID, dict[str, tuple[Decimal, str, str]]] = defaultdict(dict)
        labels: dict[uuid.UUID, str] = {}

        if not custom_items:
            return price_matrix, labels

        # Collect all ILIKE patterns across all custom items
        item_keywords: dict[uuid.UUID, list[str]] = {}
        all_patterns: list[str] = []

        for item in custom_items:
            text = item.custom_name or ""
            labels[item.id] = text
            keywords = self._extract_keywords(text)
            item_keywords[item.id] = keywords
            all_patterns.extend(keywords)

        if not all_patterns:
            return price_matrix, labels

        # Single DB query: find all candidate products matching any keyword
        unique_patterns = list(set(all_patterns))
        candidates_result = await session.execute(
            select(Product).where(
                or_(*[Product.name.ilike(f"%{pat}%") for pat in unique_patterns])
            )
        )
        all_candidates = list(candidates_result.scalars().all())

        if not all_candidates:
            return price_matrix, labels

        # For each custom item, filter candidates via fuzzy matching (cross-brand)
        matched_product_ids: set[uuid.UUID] = set()
        item_matched_products: dict[uuid.UUID, list[Product]] = defaultdict(list)

        for item in custom_items:
            keywords = item_keywords.get(item.id, [])
            custom_norm = _normalize_product_name(item.custom_name or "")

            for candidate in all_candidates:
                # Quick keyword pre-filter: at least one keyword must appear in candidate name
                cand_lower = candidate.name.lower()
                if not any(kw in cand_lower for kw in keywords):
                    continue

                cand_norm = _normalize_product_name(candidate.name)
                # Use relaxed threshold for cross-brand matching
                if _names_match(custom_norm, cand_norm, threshold=0.55):
                    item_matched_products[item.id].append(candidate)
                    matched_product_ids.add(candidate.id)

        if not matched_product_ids:
            return price_matrix, labels

        # Fetch active offers for all matched products in one query
        offers_result = await session.execute(
            select(Offer)
            .options(joinedload(Offer.chain))
            .where(
                Offer.product_id.in_(list(matched_product_ids)),
                Offer.valid_from <= today,
                Offer.valid_to >= today,
            )
            .order_by(Offer.offer_price)
        )
        all_offers = offers_result.unique().scalars().all()

        # Index offers by product_id
        offers_by_product: dict[uuid.UUID, list] = defaultdict(list)
        for offer in all_offers:
            offers_by_product[offer.product_id].append(offer)

        # For each custom item, find cheapest offer per chain among matched products
        for item in custom_items:
            matched = item_matched_products.get(item.id, [])
            for product in matched:
                for offer in offers_by_product.get(product.id, []):
                    chain_name = offer.chain.name if offer.chain else "Unknown"
                    existing = price_matrix[item.id].get(chain_name)
                    if existing is None or offer.offer_price < existing[0]:
                        price_matrix[item.id][chain_name] = (
                            offer.offer_price,
                            chain_name,
                            product.name,
                        )

        return price_matrix, labels

    async def optimize(
        self,
        user_id: uuid.UUID,
        session: AsyncSession,
    ) -> TripOptimizationResult:
        """Analyse the user's shopping list and return optimisation results."""
        today = date.today()

        # 1. Fetch ALL unchecked shopping list items
        sl_result = await session.execute(
            select(ShoppingListItem)
            .options(joinedload(ShoppingListItem.product))
            .where(
                ShoppingListItem.user_id == user_id,
                ShoppingListItem.checked.is_(False),
            )
        )
        items = sl_result.unique().scalars().all()

        # Split into product-linked and custom-name items
        product_items = [i for i in items if i.product_id is not None]
        custom_items = [i for i in items if i.product_id is None and i.custom_name]

        if not product_items and not custom_items:
            return TripOptimizationResult(
                single_store_best=None,
                multi_store_plan=[],
                single_store_total=Decimal("0"),
                multi_store_total=Decimal("0"),
                potential_savings=Decimal("0"),
                all_single_stores=[],
                items_total=0,
                items_not_covered=0,
            )

        product_ids = [i.product_id for i in product_items]

        # 2. Fetch active offers for product-linked items
        price_matrix: dict[uuid.UUID, dict[str, tuple[Decimal, str]]] = defaultdict(dict)

        if product_ids:
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

            for offer in all_offers:
                chain_name = offer.chain.name if offer.chain else "Unknown"
                pid = offer.product_id
                if chain_name not in price_matrix[pid]:
                    price_matrix[pid][chain_name] = (offer.offer_price, chain_name)

        # Product name lookup for product-linked items
        product_names: dict[uuid.UUID, str] = {}
        for item in product_items:
            product_names[item.product_id] = (
                item.product.name if item.product else item.custom_name or "Unknown"
            )

        # 3. Resolve custom-name items via fuzzy matching
        custom_price_matrix, custom_labels = await self._resolve_custom_items(
            custom_items, session, today,
        )

        # Track which custom items are search-term items (for frontend display)
        search_terms: dict[uuid.UUID, str] = {}  # item key -> search term
        # Track matched product name per (item_id, chain) for display
        custom_product_names: dict[uuid.UUID, dict[str, str]] = defaultdict(dict)

        for item in custom_items:
            search_terms[item.id] = item.custom_name or ""
            for chain_name, (price, cname, prod_name) in custom_price_matrix.get(item.id, {}).items():
                custom_product_names[item.id][chain_name] = prod_name

        # Merge into unified structures
        # For custom items, use item.id as key in price_matrix (no product_id)
        custom_pm: dict[uuid.UUID, dict[str, tuple[Decimal, str]]] = {}
        for item_id, chain_data in custom_price_matrix.items():
            custom_pm[item_id] = {
                chain: (price, cname)
                for chain, (price, cname, _pname) in chain_data.items()
            }

        # Get all unique chains across both matrices
        all_chains: set[str] = set()
        for chain_prices in price_matrix.values():
            all_chains.update(chain_prices.keys())
        for chain_prices in custom_pm.values():
            all_chains.update(chain_prices.keys())

        # 4. Single-store strategy: for each chain, sum what's available
        single_store_results: list[StoreTrip] = []
        for chain_name in sorted(all_chains):
            trip = StoreTrip(chain_name=chain_name)

            # Product-linked items
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

            # Custom-name items
            for item in custom_items:
                if chain_name in custom_pm.get(item.id, {}):
                    price, _ = custom_pm[item.id][chain_name]
                    item_total = price * item.quantity
                    matched_name = custom_product_names.get(item.id, {}).get(chain_name, item.custom_name or "Unknown")
                    trip.items.append(TripItem(
                        product_name=matched_name,
                        offer_price=item_total,
                        chain_name=chain_name,
                        search_term=item.custom_name,
                    ))
                    trip.total += item_total

            trip.items_covered = len(trip.items)
            if trip.items:
                single_store_results.append(trip)

        # Best single store (most items covered, then cheapest)
        single_store_results.sort(key=lambda t: (-len(t.items), t.total))
        single_store_best = single_store_results[0] if single_store_results else None

        # 5. Multi-store strategy: for each item, pick the cheapest chain
        multi_store_map: dict[str, StoreTrip] = {}
        multi_total = Decimal("0")

        # Product-linked items
        for item in product_items:
            pid = item.product_id
            chain_prices = price_matrix.get(pid, {})
            if not chain_prices:
                continue
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

        # Custom-name items
        for item in custom_items:
            chain_prices = custom_pm.get(item.id, {})
            if not chain_prices:
                continue
            best_chain, (best_price, _) = min(
                chain_prices.items(), key=lambda x: x[1][0]
            )
            item_total = best_price * item.quantity
            matched_name = custom_product_names.get(item.id, {}).get(best_chain, item.custom_name or "Unknown")
            if best_chain not in multi_store_map:
                multi_store_map[best_chain] = StoreTrip(chain_name=best_chain)
            multi_store_map[best_chain].items.append(TripItem(
                product_name=matched_name,
                offer_price=item_total,
                chain_name=best_chain,
                search_term=item.custom_name,
            ))
            multi_store_map[best_chain].total += item_total
            multi_total += item_total

        multi_store_plan = sorted(multi_store_map.values(), key=lambda t: t.chain_name)

        single_total = single_store_best.total if single_store_best else Decimal("0")
        savings = single_total - multi_total if single_total > multi_total else Decimal("0")

        items_total = len(product_items) + len(custom_items)
        items_with_offers = (
            sum(1 for pid in product_ids if price_matrix.get(pid))
            + sum(1 for item in custom_items if custom_pm.get(item.id))
        )
        items_not_covered = items_total - items_with_offers

        return TripOptimizationResult(
            single_store_best=single_store_best,
            multi_store_plan=multi_store_plan,
            single_store_total=single_total,
            multi_store_total=multi_total,
            potential_savings=savings,
            all_single_stores=single_store_results,
            items_total=items_total,
            items_not_covered=items_not_covered,
        )
