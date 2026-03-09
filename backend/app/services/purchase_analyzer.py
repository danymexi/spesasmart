"""Purchase habit analysis and smart shopping list generation."""

from __future__ import annotations

import logging
import re
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.database import async_session
from app.models.offer import Offer
from app.models.product import Product
from app.models.purchase import PurchaseItem, PurchaseOrder
from app.models.user import UserWatchlist

logger = logging.getLogger(__name__)

# Lines that are not real products (bags, discounts, payment methods, etc.)
_NON_PRODUCT_RE = re.compile(
    r"(?i)"
    r"sacchett[oi]|busta|shopper|"
    r"buono|coupon|sconto|"
    r"carta\s+fedelta|fidelity|punti|"
    r"cauzione|deposito|"
    r"subtotal|contante|bancomat|"
    r"carta\s+credito|carta\s+debito|"
    r"resto\s+euro|arrotondamento|"
    r"commissione|iva\b|"
    r"reso\b|rimborso|cashback|acconto"
)


def _compute_habit_from_purchases(
    info: dict[str, Any], purchases: list[dict],
) -> dict[str, Any] | None:
    """Shared logic: given product info + purchase list, return a habit dict or None."""
    if len(purchases) < 2:
        return None

    dates = sorted(set(
        p["date"].date() if isinstance(p["date"], datetime) else p["date"]
        for p in purchases
    ))
    if len(dates) < 2:
        return None

    intervals = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
    avg_interval = sum(intervals) / len(intervals) if intervals else 0

    prices = [float(p["unit_price"]) for p in purchases if p["unit_price"] is not None]
    if not prices:
        prices = [float(p["total_price"]) for p in purchases if p["total_price"] is not None]
    avg_price = sum(prices) / len(prices) if prices else None

    last_date = max(dates)
    next_predicted = last_date + timedelta(days=avg_interval) if avg_interval > 0 else None

    return {
        **info,
        "total_purchases": len(purchases),
        "avg_interval_days": round(avg_interval, 1),
        "avg_price": round(avg_price, 2) if avg_price else None,
        "last_purchased": last_date.isoformat(),
        "next_purchase_predicted": next_predicted.isoformat() if next_predicted else None,
    }


async def compute_habits(user_id: uuid.UUID) -> list[dict[str, Any]]:
    """Compute purchase habits for a user.

    Combines two sources:
    1. Items matched to catalog products (grouped by product_id)
    2. Unmatched items (grouped by normalised external_name)

    For each product bought >= 2 times, returns:
    - product_id (None for name-based), product_name, brand, category
    - total_purchases, avg_interval_days, avg_price
    - last_purchased, next_purchase_predicted
    """
    async with async_session() as session:
        # ── Query 1: items WITH product_id ──
        stmt1 = (
            select(
                PurchaseItem.product_id,
                Product.name,
                Product.brand,
                Product.category,
                Product.image_url,
                PurchaseOrder.order_date,
                PurchaseItem.unit_price,
                PurchaseItem.total_price,
                PurchaseItem.quantity,
            )
            .join(PurchaseOrder, PurchaseItem.order_id == PurchaseOrder.id)
            .join(Product, PurchaseItem.product_id == Product.id)
            .where(
                PurchaseOrder.user_id == user_id,
                PurchaseItem.product_id.isnot(None),
            )
            .order_by(PurchaseItem.product_id, PurchaseOrder.order_date)
        )
        matched_rows = (await session.execute(stmt1)).all()

        # ── Query 2: items WITHOUT product_id (name-based) ──
        stmt2 = (
            select(
                PurchaseItem.external_name,
                PurchaseItem.brand,
                PurchaseItem.category,
                PurchaseOrder.order_date,
                PurchaseItem.unit_price,
                PurchaseItem.total_price,
                PurchaseItem.quantity,
            )
            .join(PurchaseOrder, PurchaseItem.order_id == PurchaseOrder.id)
            .where(
                PurchaseOrder.user_id == user_id,
                PurchaseItem.product_id.is_(None),
            )
            .order_by(PurchaseItem.external_name, PurchaseOrder.order_date)
        )
        unmatched_rows = (await session.execute(stmt2)).all()

    # ── Process matched (product_id) items ──
    product_purchases: dict[uuid.UUID, list[dict]] = {}
    product_info: dict[uuid.UUID, dict] = {}

    for pid, name, brand, category, image_url, order_date, unit_price, total_price, qty in matched_rows:
        if pid not in product_purchases:
            product_purchases[pid] = []
            product_info[pid] = {
                "product_id": str(pid),
                "product_name": name,
                "brand": brand,
                "category": category,
                "image_url": image_url,
            }
        product_purchases[pid].append({
            "date": order_date,
            "unit_price": unit_price,
            "total_price": total_price,
            "quantity": qty,
        })

    # Track normalised names that already have a product_id match
    matched_norm_names: set[str] = set()
    for info in product_info.values():
        matched_norm_names.add(info["product_name"].strip().upper())

    habits = []
    for pid, purchases in product_purchases.items():
        habit = _compute_habit_from_purchases(product_info[pid], purchases)
        if habit:
            habits.append(habit)

    # ── Process unmatched (name-based) items ──
    # Group by normalised name: UPPER(TRIM(external_name))
    name_purchases: dict[str, list[dict]] = defaultdict(list)
    # Track the most frequent original spelling per normalised name
    name_spelling_count: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    name_brand: dict[str, str | None] = {}
    name_category: dict[str, str | None] = {}

    for ext_name, brand, category, order_date, unit_price, total_price, qty in unmatched_rows:
        if not ext_name or not ext_name.strip():
            continue
        # Filter non-product lines
        if _NON_PRODUCT_RE.search(ext_name):
            continue

        norm = ext_name.strip().upper()

        # Skip if this name is already covered by a product_id match
        if norm in matched_norm_names:
            continue

        name_purchases[norm].append({
            "date": order_date,
            "unit_price": unit_price,
            "total_price": total_price,
            "quantity": qty,
        })
        name_spelling_count[norm][ext_name.strip()] += 1
        if norm not in name_brand:
            name_brand[norm] = brand
        if norm not in name_category:
            name_category[norm] = category

    for norm, purchases in name_purchases.items():
        # Pick the most frequent original spelling
        best_spelling = max(name_spelling_count[norm], key=name_spelling_count[norm].get)  # type: ignore[arg-type]
        info = {
            "product_id": None,
            "product_name": best_spelling,
            "brand": name_brand.get(norm),
            "category": name_category.get(norm),
            "image_url": None,
        }
        habit = _compute_habit_from_purchases(info, purchases)
        if habit:
            habits.append(habit)

    # Sort by next_purchase_predicted (soonest first)
    habits.sort(key=lambda h: h.get("next_purchase_predicted") or "9999-12-31")
    return habits


async def generate_smart_list(user_id: uuid.UUID) -> list[dict[str, Any]]:
    """Generate a smart shopping list based on purchase patterns.

    Urgency levels:
    - alta: product overdue by > 3 days (interval exceeded)
    - media: due within 7 days
    - bassa: due within 14 days

    Each suggestion includes the best current price from the catalog.
    """
    habits = await compute_habits(user_id)
    if not habits:
        return []

    # Fetch watchlist product IDs for this user
    watchlist_pids: set[str] = set()
    async with async_session() as session:
        wl_stmt = select(UserWatchlist.product_id).where(
            UserWatchlist.user_id == user_id
        )
        wl_rows = (await session.execute(wl_stmt)).scalars().all()
        watchlist_pids = {str(pid) for pid in wl_rows}

    today = date.today()
    suggestions = []

    # Collect all product_ids that need offer lookup
    product_ids_to_check: list[str] = [
        h["product_id"] for h in habits if h["product_id"] is not None
    ]

    # Batch-fetch best offers for all products in one query
    best_offers: dict[str, tuple[float, str | None]] = {}
    if product_ids_to_check:
        async with async_session() as session:
            from app.models.chain import Chain

            for pid_str in product_ids_to_check:
                stmt = (
                    select(Offer.offer_price, Chain.name)
                    .join(Chain, Offer.chain_id == Chain.id)
                    .where(
                        Offer.product_id == uuid.UUID(pid_str),
                        Offer.valid_from <= today,
                        Offer.valid_to >= today,
                    )
                    .order_by(Offer.offer_price)
                    .limit(1)
                )
                result = await session.execute(stmt)
                row = result.first()
                if row:
                    best_offers[pid_str] = (float(row[0]), row[1])

    for habit in habits:
        next_pred_str = habit.get("next_purchase_predicted")
        days_until: int | None = None
        urgency: str | None = None

        if next_pred_str:
            next_pred = date.fromisoformat(next_pred_str)
            days_until = (next_pred - today).days

            if days_until < -3:
                urgency = "alta"
            elif days_until <= 7:
                urgency = "media"
            elif days_until <= 14:
                urgency = "bassa"
            # days_until > 14 → urgency stays None

        product_id = habit["product_id"]

        best_price = None
        best_chain = None
        savings = None
        in_watchlist = False

        if product_id is not None:
            in_watchlist = product_id in watchlist_pids
            offer = best_offers.get(product_id)
            if offer:
                best_price, best_chain = offer
                if habit["avg_price"] and best_price < habit["avg_price"]:
                    savings = round(habit["avg_price"] - best_price, 2)

        suggestions.append({
            **habit,
            "urgency": urgency,
            "days_until_due": days_until,
            "best_current_price": best_price,
            "best_chain": best_chain,
            "savings_vs_avg": savings,
            "in_watchlist": in_watchlist,
        })

    # Sort: urgent first (alta=0, media=1, bassa=2), then non-urgent (3)
    # Within same urgency group, sort by days_until_due (soonest first)
    # Non-urgent items sort by next_purchase_predicted
    urgency_order = {"alta": 0, "media": 1, "bassa": 2}

    def _sort_key(s: dict) -> tuple:
        urg = urgency_order.get(s["urgency"], 3) if s["urgency"] else 3
        days = s["days_until_due"] if s["days_until_due"] is not None else 9999
        return (urg, days)

    suggestions.sort(key=_sort_key)
    return suggestions
