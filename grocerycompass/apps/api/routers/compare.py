import uuid
from itertools import combinations

from fastapi import APIRouter, Depends, HTTPException
from geoalchemy2.functions import ST_DWithin
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.shopping_list import ShoppingList, ListItem
from models.product import StoreProduct
from models.store import Store
from models.chain import Chain
from schemas.compare import (
    CompareRequest, CompareResponse,
    SingleStoreResult, MultiStoreResult, MultiStoreAssignment, StoreBreakdownItem,
)
from schemas.common import ResponseModel

router = APIRouter()


@router.post("/{list_id}/compare", response_model=ResponseModel[CompareResponse])
async def compare_prices(
    list_id: uuid.UUID,
    req: CompareRequest,
    db: AsyncSession = Depends(get_db),
):
    # Get list items
    sl = await db.get(ShoppingList, list_id)
    if not sl:
        raise HTTPException(status_code=404, detail="Lista non trovata")

    items_result = await db.execute(
        select(ListItem).where(ListItem.list_id == list_id).where(ListItem.canonical_product_id.isnot(None))
    )
    items = items_result.scalars().all()
    if not items:
        raise HTTPException(status_code=400, detail="La lista non contiene prodotti per il confronto")

    # Find nearby stores
    radius_meters = req.radius_km * 1000
    stores_query = (
        select(
            Store, Chain,
            func.ST_Distance(
                Store.geom,
                func.ST_GeogFromText(f"POINT({req.lng} {req.lat})")
            ).label("distance_m"),
        )
        .join(Chain, Store.chain_id == Chain.id)
        .where(Store.is_active == True)
        .where(func.ST_DWithin(
            Store.geom,
            func.ST_GeogFromText(f"POINT({req.lng} {req.lat})"),
            radius_meters,
        ))
        .order_by(text("distance_m"))
    )
    stores_result = await db.execute(stores_query)
    nearby = stores_result.all()

    if not nearby:
        raise HTTPException(status_code=404, detail="Nessun negozio trovato nel raggio specificato")

    # Build price lookup: canonical_product_id -> store_id -> best_price
    product_ids = [item.canonical_product_id for item in items]
    prices_result = await db.execute(
        select(StoreProduct)
        .where(StoreProduct.canonical_product_id.in_(product_ids))
        .where(StoreProduct.in_stock == True)
    )
    all_prices = prices_result.scalars().all()

    # Map: product_id -> chain_id -> effective_price
    price_map: dict[uuid.UUID, dict[uuid.UUID, float]] = {}
    for sp in all_prices:
        pid = sp.canonical_product_id
        cid = sp.chain_id
        effective = float(sp.price_discounted) if sp.price_discounted else float(sp.price)
        if pid not in price_map:
            price_map[pid] = {}
        if cid not in price_map[pid] or effective < price_map[pid][cid]:
            price_map[pid][cid] = effective

    # Single-store ranking
    single_results = []
    for store, chain, distance_m in nearby:
        total = 0.0
        covered = 0
        for item in items:
            pid = item.canonical_product_id
            if pid in price_map and chain.id in price_map[pid]:
                total += price_map[pid][chain.id] * float(item.quantity)
                covered += 1

        coverage = (covered / len(items) * 100) if items else 0
        single_results.append(SingleStoreResult(
            store_id=store.id,
            store_name=store.name or chain.name,
            chain_slug=chain.slug,
            chain_name=chain.name,
            total=round(total, 2),
            coverage_pct=round(coverage, 1),
            missing_count=len(items) - covered,
            distance_km=round(distance_m / 1000, 1) if distance_m else None,
        ))

    single_results.sort(key=lambda x: x.total * (1 + (100 - x.coverage_pct) / 100))

    # Multi-store optimization (max 2 stores)
    multi_optimal = None
    if req.max_stores >= 2 and len(nearby) >= 2:
        # Get unique chains from nearby stores
        chain_stores: dict[uuid.UUID, tuple] = {}
        for store, chain, distance_m in nearby:
            if chain.id not in chain_stores:
                chain_stores[chain.id] = (store, chain, distance_m)

        best_combo = None
        best_total = float("inf")

        for combo in combinations(chain_stores.values(), min(req.max_stores, len(chain_stores))):
            total = 0.0
            assignments: dict[uuid.UUID, tuple] = {}  # item -> (store, chain, price)

            for item in items:
                pid = item.canonical_product_id
                best_price = None
                best_entry = None

                for store, chain, dist in combo:
                    if pid in price_map and chain.id in price_map[pid]:
                        p = price_map[pid][chain.id]
                        if best_price is None or p < best_price:
                            best_price = p
                            best_entry = (store, chain, dist)

                if best_price is not None:
                    total += best_price * float(item.quantity)
                    assignments[item.id] = (best_entry, best_price, item)

            extra_travel = (len(combo) - 1) * req.travel_cost_per_extra
            total += extra_travel

            if total < best_total:
                best_total = total
                best_combo = (combo, assignments, extra_travel)

        if best_combo and single_results:
            combo, assignments, travel_cost = best_combo
            # Group by store
            store_groups: dict[uuid.UUID, list] = {}
            for item_id, (entry, price, item) in assignments.items():
                store, chain, dist = entry
                if store.id not in store_groups:
                    store_groups[store.id] = {"store": store, "chain": chain, "items": []}
                store_groups[store.id]["items"].append(
                    StoreBreakdownItem(
                        item_name=str(item.canonical_product_id),
                        quantity=float(item.quantity),
                        price=price,
                        total=round(price * float(item.quantity), 2),
                        is_discounted=False,
                    )
                )

            multi_assignments = []
            for sid, data in store_groups.items():
                subtotal = sum(i.total for i in data["items"])
                multi_assignments.append(MultiStoreAssignment(
                    store_id=sid,
                    store_name=data["store"].name or data["chain"].name,
                    chain_slug=data["chain"].slug,
                    items=data["items"],
                    subtotal=round(subtotal, 2),
                ))

            savings = single_results[0].total - best_total if single_results else 0

            multi_optimal = MultiStoreResult(
                stores=multi_assignments,
                total=round(best_total, 2),
                travel_cost=travel_cost,
                savings_vs_best_single=round(max(0, savings), 2),
            )

    return ResponseModel(data=CompareResponse(
        list_id=list_id,
        single_store_ranking=single_results,
        multi_store_optimal=multi_optimal,
    ))
