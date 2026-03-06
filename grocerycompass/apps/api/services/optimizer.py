"""Price comparison and multi-store optimization engine."""

from dataclasses import dataclass
from itertools import combinations


@dataclass
class PriceEntry:
    store_id: str
    chain_slug: str
    price: float
    price_discounted: float | None
    in_stock: bool

    @property
    def effective_price(self) -> float:
        return self.price_discounted if self.price_discounted else self.price


@dataclass
class ListItemForCompare:
    id: str
    canonical_product_id: str | None
    free_text_name: str | None
    quantity: float


@dataclass
class StoreComparison:
    store_id: str
    store_name: str
    chain_slug: str
    total: float
    coverage_pct: float
    missing_items: list[ListItemForCompare]
    item_breakdown: list[dict]


@dataclass
class MultiStoreComparison:
    stores: list[dict]
    total: float
    assignments: dict  # item_id -> (store_id, price)
    travel_cost: float


def compute_single_store_costs(
    items: list[ListItemForCompare],
    stores: list[dict],
    price_map: dict[str, dict[str, float]],
) -> list[StoreComparison]:
    """
    For each store, compute total cost for all items in the list.
    price_map: canonical_product_id -> chain_slug -> effective_price
    """
    results = []
    catalog_items = [i for i in items if i.canonical_product_id]

    for store in stores:
        total = 0.0
        covered = 0
        missing = []
        breakdown = []

        for item in catalog_items:
            pid = item.canonical_product_id
            chain = store["chain_slug"]

            if pid in price_map and chain in price_map[pid]:
                price = price_map[pid][chain]
                item_cost = price * item.quantity
                total += item_cost
                covered += 1
                breakdown.append({
                    "item_id": item.id,
                    "price": price,
                    "total": round(item_cost, 2),
                })
            else:
                missing.append(item)

        coverage = (covered / len(catalog_items) * 100) if catalog_items else 0

        results.append(StoreComparison(
            store_id=store["id"],
            store_name=store["name"],
            chain_slug=store["chain_slug"],
            total=round(total, 2),
            coverage_pct=round(coverage, 1),
            missing_items=missing,
            item_breakdown=breakdown,
        ))

    # Sort by adjusted total (penalize low coverage)
    results.sort(key=lambda x: x.total * (1 + (100 - x.coverage_pct) / 100))
    return results


def compute_multi_store_optimization(
    items: list[ListItemForCompare],
    stores: list[dict],
    price_map: dict[str, dict[str, float]],
    max_stores: int = 2,
    travel_cost_per_extra: float = 0.0,
) -> list[MultiStoreComparison]:
    """Find optimal combination of N stores that minimizes total cost."""
    catalog_items = [i for i in items if i.canonical_product_id]
    all_combos = []

    for n in range(1, max_stores + 1):
        for store_combo in combinations(stores, min(n, len(stores))):
            total = 0.0
            assignments = {}

            for item in catalog_items:
                pid = item.canonical_product_id
                best_price = None
                best_store = None

                for store in store_combo:
                    chain = store["chain_slug"]
                    if pid in price_map and chain in price_map[pid]:
                        p = price_map[pid][chain]
                        if best_price is None or p < best_price:
                            best_price = p
                            best_store = store

                if best_price is not None:
                    total += best_price * item.quantity
                    assignments[item.id] = (best_store["id"], best_price)

            extra_travel = (len(store_combo) - 1) * travel_cost_per_extra
            total += extra_travel

            all_combos.append(MultiStoreComparison(
                stores=[s for s in store_combo],
                total=round(total, 2),
                assignments=assignments,
                travel_cost=extra_travel,
            ))

    all_combos.sort(key=lambda x: x.total)
    return all_combos
