"""Iperal Spesa Online — order history scraper.

Uses httpx with direct API login (or session from iperal_session_helper)
to fetch order history.

NOTE: The actual order endpoints need to be confirmed by running
discover_iperal_orders.py first.
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.scrapers.order_scraper_base import Order, OrderItem, OrderScraperBase

logger = logging.getLogger(__name__)

BASE_URL = "https://www.iperalspesaonline.it"
AUTH_LOGIN_URL = f"{BASE_URL}/ebsn/api/auth/login"
AUTH_TEST_URL = f"{BASE_URL}/ebsn/api/auth/test"


class IperalOrderScraper(OrderScraperBase):
    """Scrape order history from Iperal Spesa Online."""

    chain_slug = "iperal"

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._logged_in = False

    async def login(self, email: str, password: str) -> bool:
        """Authenticate via the Iperal API."""
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=30.0,
            follow_redirects=True,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": f"{BASE_URL}/",
            },
        )

        try:
            # Attempt API login
            resp = await self._client.post(
                "/ebsn/api/auth/login",
                json={"email": email, "password": password},
            )

            if resp.status_code == 200:
                data = resp.json()
                user_id = (
                    data.get("data", {}).get("user", {}).get("userId")
                    or data.get("user", {}).get("userId")
                    or 0
                )
                if user_id and int(user_id) > 0:
                    self._logged_in = True
                    logger.info("Iperal: login successful (userId=%s).", user_id)
                    return True

            # Verify with auth test
            test_resp = await self._client.get("/ebsn/api/auth/test")
            if test_resp.status_code == 200:
                test_data = test_resp.json()
                user_id = (
                    test_data.get("data", {}).get("user", {}).get("userId")
                    or test_data.get("user", {}).get("userId")
                    or 0
                )
                if user_id and int(user_id) > 0:
                    self._logged_in = True
                    logger.info("Iperal: login confirmed via auth test (userId=%s).", user_id)
                    return True

            logger.warning("Iperal: login failed (status=%d).", resp.status_code)
            return False

        except Exception:
            logger.exception("Iperal: login error.")
            return False

    async def fetch_orders(self, since: datetime | None = None) -> list[Order]:
        """Fetch order history from Iperal API.

        NOTE: Actual endpoints will be confirmed after running discover_iperal_orders.py.
        """
        if not self._logged_in or not self._client:
            logger.error("Iperal: not logged in.")
            return []

        orders: list[Order] = []

        # Try candidate endpoints (to be updated after discovery)
        order_endpoints = [
            ("/ebsn/api/orders", "GET"),
            ("/ebsn/api/order/list", "GET"),
            ("/ebsn/api/order/history", "GET"),
            ("/ebsn/api/user/orders", "GET"),
            ("/ebsn/api/cart/history", "GET"),
        ]

        raw_orders = None
        for path, method in order_endpoints:
            try:
                logger.info("Iperal: trying %s %s", method, path)
                if method == "GET":
                    resp = await self._client.get(path)
                else:
                    resp = await self._client.post(path, json={})

                if resp.status_code == 200:
                    data = resp.json()
                    # Check if it looks like an order list
                    if isinstance(data, list) or (isinstance(data, dict) and any(
                        k in data for k in ("orders", "data", "results", "content")
                    )):
                        raw_orders = data
                        logger.info("Iperal: found orders at %s", path)
                        break
            except Exception:
                continue

        if not raw_orders:
            logger.warning("Iperal: no order endpoint returned data.")
            return []

        # Extract order list from response
        if isinstance(raw_orders, list):
            order_list = raw_orders
        elif isinstance(raw_orders, dict):
            order_list = (
                raw_orders.get("orders")
                or raw_orders.get("data")
                or raw_orders.get("results")
                or raw_orders.get("content")
                or []
            )
        else:
            return []

        if not isinstance(order_list, list):
            return []

        for raw in order_list:
            try:
                order = self._parse_order(raw)
                if order and (since is None or order.order_date >= since):
                    orders.append(order)
            except Exception:
                logger.exception("Iperal: failed to parse order: %s", str(raw)[:200])

        logger.info("Iperal: fetched %d orders.", len(orders))
        return orders

    def _parse_order(self, raw: dict[str, Any]) -> Order | None:
        """Parse a raw order dict into an Order."""
        order_id = str(
            raw.get("orderId")
            or raw.get("id")
            or raw.get("orderNumber")
            or raw.get("orderCode")
            or ""
        )
        if not order_id:
            return None

        # Parse date
        date_str = (
            raw.get("orderDate")
            or raw.get("date")
            or raw.get("createdAt")
            or raw.get("deliveryDate")
            or ""
        )
        try:
            if isinstance(date_str, (int, float)):
                # Epoch milliseconds
                order_date = datetime.fromtimestamp(date_str / 1000)
            else:
                order_date = datetime.fromisoformat(str(date_str).replace("Z", "+00:00"))
        except (ValueError, TypeError, OSError):
            order_date = datetime.now()

        # Total
        total = None
        for key in ("totalAmount", "total", "grandTotal", "orderTotal", "netTotal"):
            if key in raw and raw[key] is not None:
                try:
                    total = Decimal(str(raw[key]))
                except (InvalidOperation, ValueError):
                    pass
                break

        # Items
        items: list[OrderItem] = []
        raw_items = (
            raw.get("items")
            or raw.get("products")
            or raw.get("orderItems")
            or raw.get("cartItems")
            or []
        )
        for ri in raw_items:
            if isinstance(ri, dict):
                item = self._parse_item(ri)
                if item:
                    items.append(item)

        return Order(
            external_order_id=order_id,
            order_date=order_date,
            total_amount=total,
            store_name=raw.get("storeName") or raw.get("warehouseName"),
            status=raw.get("status") or raw.get("orderStatus"),
            items=items,
            raw_data=raw,
        )

    @staticmethod
    def _parse_item(raw: dict[str, Any]) -> OrderItem | None:
        name = str(
            raw.get("description")
            or raw.get("name")
            or raw.get("productName")
            or raw.get("shortDescription")
            or ""
        ).strip()
        if not name:
            return None

        qty = None
        for key in ("quantity", "qty", "requestedQuantity", "acceptedQuantity"):
            if key in raw and raw[key] is not None:
                try:
                    qty = Decimal(str(raw[key]))
                except (InvalidOperation, ValueError):
                    pass
                break

        unit_price = None
        for key in ("unitPrice", "price", "grossUnitPrice"):
            if key in raw and raw[key] is not None:
                try:
                    unit_price = Decimal(str(raw[key]))
                except (InvalidOperation, ValueError):
                    pass
                break

        total_price = None
        for key in ("totalPrice", "lineTotal", "grossTotal", "rowTotal"):
            if key in raw and raw[key] is not None:
                try:
                    total_price = Decimal(str(raw[key]))
                except (InvalidOperation, ValueError):
                    pass
                break

        return OrderItem(
            external_name=name,
            quantity=qty,
            unit_price=unit_price,
            total_price=total_price,
            external_code=raw.get("code") or raw.get("sku") or raw.get("ean"),
            brand=raw.get("brand"),
            category=raw.get("category") or raw.get("categoryDescription"),
        )

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
