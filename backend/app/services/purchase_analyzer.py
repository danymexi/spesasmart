"""Purchase habit analysis and smart shopping list generation."""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.database import async_session
from app.models.offer import Offer
from app.models.product import Product
from app.models.purchase import PurchaseItem, PurchaseOrder

logger = logging.getLogger(__name__)


async def compute_habits(user_id: uuid.UUID) -> list[dict[str, Any]]:
    """Compute purchase habits for a user.

    For each product bought >= 2 times, returns:
    - product_id, product_name, brand, category
    - total_purchases: number of times bought
    - avg_interval_days: average days between purchases
    - avg_price: average unit price paid
    - last_purchased: date of last purchase
    - next_purchase_predicted: last_purchased + avg_interval
    """
    async with async_session() as session:
        # Get all purchase items with matched products, ordered by date
        stmt = (
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
        rows = (await session.execute(stmt)).all()

    if not rows:
        return []

    # Group by product
    product_purchases: dict[uuid.UUID, list[dict]] = {}
    product_info: dict[uuid.UUID, dict] = {}

    for pid, name, brand, category, image_url, order_date, unit_price, total_price, qty in rows:
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

    habits = []
    for pid, purchases in product_purchases.items():
        if len(purchases) < 2:
            continue

        # Calculate intervals
        dates = sorted(set(p["date"].date() if isinstance(p["date"], datetime) else p["date"] for p in purchases))
        if len(dates) < 2:
            continue

        intervals = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
        avg_interval = sum(intervals) / len(intervals) if intervals else 0

        # Calculate average price
        prices = [
            float(p["unit_price"]) for p in purchases
            if p["unit_price"] is not None
        ]
        if not prices:
            prices = [
                float(p["total_price"]) for p in purchases
                if p["total_price"] is not None
            ]
        avg_price = sum(prices) / len(prices) if prices else None

        last_date = max(dates)
        next_predicted = last_date + timedelta(days=avg_interval) if avg_interval > 0 else None

        habit = {
            **product_info[pid],
            "total_purchases": len(purchases),
            "avg_interval_days": round(avg_interval, 1),
            "avg_price": round(avg_price, 2) if avg_price else None,
            "last_purchased": last_date.isoformat(),
            "next_purchase_predicted": next_predicted.isoformat() if next_predicted else None,
        }
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

    today = date.today()
    suggestions = []

    for habit in habits:
        next_pred_str = habit.get("next_purchase_predicted")
        if not next_pred_str:
            continue

        next_pred = date.fromisoformat(next_pred_str)
        days_until = (next_pred - today).days

        # Determine urgency
        if days_until < -3:
            urgency = "alta"
        elif days_until <= 7:
            urgency = "media"
        elif days_until <= 14:
            urgency = "bassa"
        else:
            continue  # Not due soon enough

        product_id = habit["product_id"]

        # Find best current price
        best_price = None
        best_chain = None
        savings = None

        async with async_session() as session:
            stmt = (
                select(Offer.offer_price, Offer.chain_id)
                .where(
                    Offer.product_id == uuid.UUID(product_id),
                    Offer.valid_from <= today,
                    Offer.valid_to >= today,
                )
                .order_by(Offer.offer_price)
                .limit(1)
            )
            result = await session.execute(stmt)
            row = result.first()
            if row:
                best_price = float(row[0])
                # Get chain name
                from app.models.chain import Chain
                chain_result = await session.execute(
                    select(Chain.name).where(Chain.id == row[1])
                )
                best_chain = chain_result.scalar_one_or_none()

                # Calculate savings vs average historical price
                if habit["avg_price"] and best_price < habit["avg_price"]:
                    savings = round(habit["avg_price"] - best_price, 2)

        suggestions.append({
            **habit,
            "urgency": urgency,
            "days_until_due": days_until,
            "best_current_price": best_price,
            "best_chain": best_chain,
            "savings_vs_avg": savings,
        })

    # Sort by urgency (alta first), then by days_until_due
    urgency_order = {"alta": 0, "media": 1, "bassa": 2}
    suggestions.sort(key=lambda s: (urgency_order.get(s["urgency"], 3), s["days_until_due"]))
    return suggestions
