"""Esselunga Spesa Online — order history scraper.

Uses Playwright to log in (session-based AngularJS SPA) and fetch order history
via the internal REST API discovered during Fase 0.

NOTE: The actual API endpoints need to be filled in after running
discover_esselunga_auth.py.  The placeholders below are based on common
patterns seen in the Esselunga e-commerce platform.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.scrapers.order_scraper_base import Order, OrderItem, OrderScraperBase

logger = logging.getLogger(__name__)

SITE_URL = "https://spesaonline.esselunga.it"
BASE_URL = f"{SITE_URL}/commerce/resources"


class EsselungaOrderScraper(OrderScraperBase):
    """Scrape order history from Esselunga Spesa Online."""

    chain_slug = "esselunga"

    def __init__(self) -> None:
        self._page = None
        self._browser = None
        self._playwright = None
        self._logged_in = False

    async def login_with_session(self, session_data: dict) -> bool:
        """Log in using a saved Playwright storageState (cookies + localStorage)."""
        try:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
            context = await self._browser.new_context(
                viewport={"width": 1280, "height": 720},
                locale="it-IT",
                timezone_id="Europe/Rome",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            context.set_default_timeout(30000)

            # Load cookies from session
            cookies = session_data.get("cookies", [])
            if cookies:
                await context.add_cookies(cookies)

            self._page = await context.new_page()

            # Navigate and verify session
            logger.info("Esselunga: loading site with saved session...")
            try:
                await self._page.goto(
                    f"{SITE_URL}/commerce/nav/supermercato/store/home",
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
            except Exception:
                pass
            await self._page.wait_for_timeout(3000)

            # Verify session is valid
            test = await self._page.evaluate(f"""async () => {{
                try {{
                    const resp = await fetch("{BASE_URL}/nav/supermercato", {{
                        headers: {{ "Accept": "application/json" }},
                        credentials: "include",
                    }});
                    return {{ ok: resp.ok, status: resp.status }};
                }} catch (e) {{ return {{ error: e.message }}; }}
            }}""")

            if test and test.get("ok"):
                self._logged_in = True
                logger.info("Esselunga: session login successful.")
                return True
            else:
                logger.warning("Esselunga: session expired or invalid: %s", test)
                return False

        except Exception:
            logger.exception("Esselunga: session login failed.")
            return False

    async def login(self, email: str, password: str) -> bool:
        """Log in via Playwright — loads the SPA, fills credentials, submits."""
        try:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
            context = await self._browser.new_context(
                viewport={"width": 1280, "height": 720},
                locale="it-IT",
                timezone_id="Europe/Rome",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            context.set_default_timeout(30000)
            self._page = await context.new_page()

            # Load login page
            logger.info("Esselunga: loading login page...")
            try:
                await self._page.goto(
                    f"{SITE_URL}/commerce/nav/supermercato/store/home",
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
            except Exception:
                pass
            await self._page.wait_for_timeout(5000)

            # Accept cookies if banner appears
            try:
                btn = self._page.locator("button:has-text('Accetta tutti')").first
                if await btn.is_visible(timeout=3000):
                    await btn.click()
                    await self._page.wait_for_timeout(1000)
            except Exception:
                pass

            # Click on "Accedi" / login button
            try:
                login_btn = self._page.locator("a:has-text('Accedi'), button:has-text('Accedi')").first
                if await login_btn.is_visible(timeout=5000):
                    await login_btn.click()
                    await self._page.wait_for_timeout(3000)
            except Exception:
                pass

            # Fill login form
            # Esselunga uses various login forms — try common selectors
            try:
                await self._page.fill('input[type="email"], input[name="username"], input[id*="email"]', email, timeout=10000)
                await self._page.fill('input[type="password"], input[name="password"]', password, timeout=5000)
                await self._page.click('button[type="submit"], input[type="submit"]', timeout=5000)
                await self._page.wait_for_timeout(5000)
            except Exception as e:
                logger.error("Esselunga: could not fill login form: %s", e)
                return False

            # Verify login by checking session
            test = await self._page.evaluate(f"""async () => {{
                try {{
                    const resp = await fetch("{BASE_URL}/nav/supermercato", {{
                        headers: {{ "Accept": "application/json" }},
                        credentials: "include",
                    }});
                    return {{ ok: resp.ok, status: resp.status }};
                }} catch (e) {{ return {{ error: e.message }}; }}
            }}""")

            if test and test.get("ok"):
                self._logged_in = True
                logger.info("Esselunga: login successful.")
                return True
            else:
                logger.warning("Esselunga: login verification failed: %s", test)
                return False

        except Exception:
            logger.exception("Esselunga: login failed.")
            return False

    async def fetch_orders(self, since: datetime | None = None) -> list[Order]:
        """Fetch order history via the Esselunga API.

        NOTE: The actual endpoint paths need to be discovered by running
        discover_esselunga_auth.py first. These are placeholder patterns.
        """
        if not self._logged_in or not self._page:
            logger.error("Esselunga: not logged in.")
            return []

        orders: list[Order] = []

        # Try known order history endpoints
        # These will be updated after API discovery
        order_endpoints = [
            f"{BASE_URL}/order/list",
            f"{BASE_URL}/order/history",
            f"{BASE_URL}/user/orders",
        ]

        raw_orders = None
        for endpoint in order_endpoints:
            logger.info("Esselunga: trying order endpoint %s", endpoint)
            result = await self._js_fetch_json(endpoint)
            if result and not result.get("__error"):
                raw_orders = result
                logger.info("Esselunga: found orders at %s", endpoint)
                break

        if not raw_orders:
            logger.warning("Esselunga: no order endpoint returned data.")
            return []

        # Parse orders — adapt based on actual API response structure
        order_list = raw_orders if isinstance(raw_orders, list) else raw_orders.get("orders", raw_orders.get("data", []))
        if not isinstance(order_list, list):
            logger.warning("Esselunga: unexpected order response format: %s", type(order_list))
            return []

        for raw in order_list:
            try:
                order = self._parse_order(raw)
                if order and (since is None or order.order_date >= since):
                    orders.append(order)
            except Exception:
                logger.exception("Esselunga: failed to parse order: %s", str(raw)[:200])

        logger.info("Esselunga: fetched %d orders.", len(orders))
        return orders

    def _parse_order(self, raw: dict[str, Any]) -> Order | None:
        """Parse a raw order dict into an Order dataclass.

        This is a best-effort parser — actual field names depend on the API.
        """
        order_id = str(
            raw.get("orderId")
            or raw.get("id")
            or raw.get("orderNumber")
            or ""
        )
        if not order_id:
            return None

        # Parse date
        date_str = raw.get("orderDate") or raw.get("date") or raw.get("createdAt") or ""
        try:
            order_date = datetime.fromisoformat(str(date_str).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            order_date = datetime.now()

        # Total
        total = None
        for key in ("totalAmount", "total", "grandTotal", "orderTotal"):
            if key in raw and raw[key] is not None:
                try:
                    total = Decimal(str(raw[key]))
                except (InvalidOperation, ValueError):
                    pass
                break

        # Items
        items: list[OrderItem] = []
        raw_items = raw.get("items") or raw.get("products") or raw.get("orderItems") or []
        for ri in raw_items:
            item = self._parse_item(ri)
            if item:
                items.append(item)

        return Order(
            external_order_id=order_id,
            order_date=order_date,
            total_amount=total,
            store_name=raw.get("storeName") or raw.get("store"),
            status=raw.get("status") or raw.get("orderStatus"),
            items=items,
            raw_data=raw,
        )

    @staticmethod
    def _parse_item(raw: dict[str, Any]) -> OrderItem | None:
        name = str(raw.get("description") or raw.get("name") or raw.get("productName") or "").strip()
        if not name:
            return None

        qty = None
        for key in ("quantity", "qty", "amount"):
            if key in raw and raw[key] is not None:
                try:
                    qty = Decimal(str(raw[key]))
                except (InvalidOperation, ValueError):
                    pass
                break

        unit_price = None
        for key in ("unitPrice", "price", "pricePerUnit"):
            if key in raw and raw[key] is not None:
                try:
                    unit_price = Decimal(str(raw[key]))
                except (InvalidOperation, ValueError):
                    pass
                break

        total_price = None
        for key in ("totalPrice", "lineTotal", "subtotal"):
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
            external_code=raw.get("code") or raw.get("sku"),
            brand=raw.get("brand"),
            category=raw.get("category"),
        )

    async def _js_fetch_json(self, url: str, body: dict | None = None) -> dict | None:
        """Make an API call from within the Playwright page context."""
        if body is not None:
            body_json = json.dumps(body)
            script = f"""async () => {{
                try {{
                    const resp = await fetch("{url}", {{
                        method: "POST",
                        headers: {{ "Accept": "application/json", "Content-Type": "application/json" }},
                        credentials: "include",
                        body: {json.dumps(body_json)},
                    }});
                    if (!resp.ok) return {{ __error: true, status: resp.status }};
                    return await resp.json();
                }} catch (e) {{ return {{ __error: true, message: e.message }}; }}
            }}"""
        else:
            script = f"""async () => {{
                try {{
                    const resp = await fetch("{url}", {{
                        headers: {{ "Accept": "application/json" }},
                        credentials: "include",
                    }});
                    if (!resp.ok) return {{ __error: true, status: resp.status }};
                    return await resp.json();
                }} catch (e) {{ return {{ __error: true, message: e.message }}; }}
            }}"""

        result = await self._page.evaluate(script)
        if result and result.get("__error"):
            logger.debug("Esselunga API error for %s: %s", url, str(result)[:200])
            return None
        return result

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
