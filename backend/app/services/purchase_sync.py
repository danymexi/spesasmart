"""Purchase history sync orchestrator.

Handles: decrypt credentials → login → fetch orders → save to DB → match items.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import async_session
from app.models.purchase import (
    PurchaseItem,
    PurchaseOrder,
    PurchaseSyncLog,
    SupermarketCredential,
)
from app.scrapers.order_scraper_base import Order, OrderScraperBase
from app.services.credential_encryption import decrypt

logger = logging.getLogger(__name__)

# Scraper registry
SCRAPER_MAP: dict[str, type] = {}


def _get_scraper(chain_slug: str) -> OrderScraperBase:
    """Instantiate the right scraper for a chain."""
    if not SCRAPER_MAP:
        # Lazy import to avoid circular deps
        from app.scrapers.esselunga_order_scraper import EsselungaOrderScraper
        from app.scrapers.iperal_order_scraper import IperalOrderScraper
        SCRAPER_MAP["esselunga"] = EsselungaOrderScraper
        SCRAPER_MAP["iperal"] = IperalOrderScraper

    cls = SCRAPER_MAP.get(chain_slug)
    if not cls:
        raise ValueError(f"No order scraper for chain '{chain_slug}'")
    return cls()


class PurchaseSyncService:
    """Orchestrates purchase history syncing for users."""

    @staticmethod
    async def sync_user_chain(user_id: uuid.UUID, chain_slug: str) -> dict[str, Any]:
        """Sync a single user's orders for a specific chain.

        Returns a summary dict with keys: status, orders_fetched, items_fetched, items_matched, error.
        """
        async with async_session() as session:
            # Load credentials
            result = await session.execute(
                select(SupermarketCredential).where(
                    SupermarketCredential.user_id == user_id,
                    SupermarketCredential.chain_slug == chain_slug,
                )
            )
            cred = result.scalar_one_or_none()
            if not cred:
                return {"status": "error", "error": "No credentials found."}
            if not cred.is_valid:
                return {"status": "error", "error": f"Credentials marked invalid: {cred.last_error}"}

            # Create sync log entry
            sync_log = PurchaseSyncLog(
                user_id=user_id,
                chain_slug=chain_slug,
            )
            session.add(sync_log)
            await session.commit()
            await session.refresh(sync_log)

        # Decrypt credentials (never log them)
        try:
            email = decrypt(cred.encrypted_email)
            password = decrypt(cred.encrypted_password)
        except ValueError as e:
            await _finish_sync_log(sync_log.id, "failed", error_message=str(e))
            await _mark_cred_invalid(cred.id, str(e))
            return {"status": "error", "error": str(e)}

        # Login + fetch orders
        scraper = _get_scraper(chain_slug)
        try:
            logged_in = await scraper.login(email, password)
            if not logged_in:
                error = "Login failed — check credentials."
                await _finish_sync_log(sync_log.id, "failed", error_message=error)
                await _mark_cred_invalid(cred.id, error)
                return {"status": "error", "error": error}

            # Fetch orders since last sync
            orders = await scraper.fetch_orders(since=cred.last_synced_at)

        except Exception as e:
            error = f"Scraper error: {e}"
            logger.exception("Sync failed for user=%s chain=%s", user_id, chain_slug)
            await _finish_sync_log(sync_log.id, "failed", error_message=error)
            return {"status": "error", "error": error}
        finally:
            await scraper.close()

        # Save orders + items to DB
        orders_saved = 0
        items_saved = 0
        items_matched = 0

        async with async_session() as session:
            for order in orders:
                try:
                    o_saved, i_saved, i_matched = await _save_order(
                        session, user_id, chain_slug, order
                    )
                    orders_saved += o_saved
                    items_saved += i_saved
                    items_matched += i_matched
                except Exception:
                    logger.exception(
                        "Failed to save order %s for user=%s",
                        order.external_order_id, user_id,
                    )

            # Update credential last_synced_at and mark valid
            result = await session.execute(
                select(SupermarketCredential).where(SupermarketCredential.id == cred.id)
            )
            cred_obj = result.scalar_one()
            cred_obj.last_synced_at = datetime.now(timezone.utc)
            cred_obj.is_valid = True
            cred_obj.last_error = None
            await session.commit()

        # Finish sync log
        await _finish_sync_log(
            sync_log.id, "success",
            orders_fetched=orders_saved,
            items_fetched=items_saved,
            items_matched=items_matched,
        )

        return {
            "status": "success",
            "orders_fetched": orders_saved,
            "items_fetched": items_saved,
            "items_matched": items_matched,
        }

    @staticmethod
    async def sync_all_users() -> int:
        """Sync all users with valid credentials. Returns total syncs performed."""
        async with async_session() as session:
            result = await session.execute(
                select(SupermarketCredential).where(
                    SupermarketCredential.is_valid.is_(True)
                )
            )
            creds = result.scalars().all()

        synced = 0
        for cred in creds:
            try:
                await PurchaseSyncService.sync_user_chain(cred.user_id, cred.chain_slug)
                synced += 1
            except Exception:
                logger.exception(
                    "Sync failed for user=%s chain=%s", cred.user_id, cred.chain_slug
                )
            # Rate limit between users
            await asyncio.sleep(0.1)

        return synced


async def _save_order(
    session,
    user_id: uuid.UUID,
    chain_slug: str,
    order: Order,
) -> tuple[int, int, int]:
    """Save an order and its items to the DB. Returns (orders_saved, items_saved, items_matched)."""

    # Check if order already exists (upsert)
    existing = await session.execute(
        select(PurchaseOrder).where(
            PurchaseOrder.user_id == user_id,
            PurchaseOrder.chain_slug == chain_slug,
            PurchaseOrder.external_order_id == order.external_order_id,
        )
    )
    if existing.scalar_one_or_none():
        # Order already exists — skip
        return (0, 0, 0)

    # Create new order
    db_order = PurchaseOrder(
        user_id=user_id,
        chain_slug=chain_slug,
        external_order_id=order.external_order_id,
        order_date=order.order_date,
        total_amount=order.total_amount,
        store_name=order.store_name,
        status=order.status,
        raw_data=order.raw_data,
    )
    session.add(db_order)
    await session.flush()  # Get the order ID

    items_saved = 0
    items_matched = 0

    for item in order.items:
        # Try to match item to a catalog product
        matched_product_id = await _match_item_to_product(session, item.external_name, item.external_code)

        db_item = PurchaseItem(
            order_id=db_order.id,
            product_id=matched_product_id,
            external_name=item.external_name,
            external_code=item.external_code,
            quantity=item.quantity,
            unit_price=item.unit_price,
            total_price=item.total_price,
            brand=item.brand,
            category=item.category,
        )
        session.add(db_item)
        items_saved += 1
        if matched_product_id:
            items_matched += 1

    await session.commit()
    return (1, items_saved, items_matched)


async def _match_item_to_product(
    session,
    name: str,
    code: str | None,
) -> uuid.UUID | None:
    """Try to match a purchase item to a product in the catalog.

    Strategy:
    1. Exact barcode match
    2. Fuzzy name match via ProductMatcher
    """
    from app.models.product import Product

    # 1. Barcode match
    if code:
        result = await session.execute(
            select(Product.id).where(Product.barcode == code).limit(1)
        )
        product_id = result.scalar_one_or_none()
        if product_id:
            return product_id

    # 2. Fuzzy name match
    try:
        from rapidfuzz import fuzz
        from sqlalchemy import func

        # Search for products with similar names
        # Use a simple LIKE for initial filtering, then fuzzy score
        search_term = name[:50]  # Use first 50 chars for LIKE
        result = await session.execute(
            select(Product.id, Product.name)
            .where(Product.name.ilike(f"%{search_term[:20]}%"))
            .limit(20)
        )
        candidates = result.all()

        best_match = None
        best_score = 0
        for pid, pname in candidates:
            score = fuzz.token_sort_ratio(name.lower(), pname.lower())
            if score > best_score and score >= 75:
                best_score = score
                best_match = pid

        return best_match

    except Exception:
        return None


async def _finish_sync_log(
    log_id: uuid.UUID,
    status: str,
    orders_fetched: int = 0,
    items_fetched: int = 0,
    items_matched: int = 0,
    error_message: str | None = None,
) -> None:
    """Update a sync log entry with final results."""
    async with async_session() as session:
        result = await session.execute(
            select(PurchaseSyncLog).where(PurchaseSyncLog.id == log_id)
        )
        log = result.scalar_one_or_none()
        if log:
            log.status = status
            log.finished_at = datetime.now(timezone.utc)
            log.orders_fetched = orders_fetched
            log.items_fetched = items_fetched
            log.items_matched = items_matched
            log.error_message = error_message
            await session.commit()


async def _mark_cred_invalid(cred_id: uuid.UUID, error: str) -> None:
    """Mark credentials as invalid."""
    async with async_session() as session:
        result = await session.execute(
            select(SupermarketCredential).where(SupermarketCredential.id == cred_id)
        )
        cred = result.scalar_one_or_none()
        if cred:
            cred.is_valid = False
            cred.last_error = error
            await session.commit()
