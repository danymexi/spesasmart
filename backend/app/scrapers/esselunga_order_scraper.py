"""Esselunga Area Utenti — receipt/shopping movements scraper.

Scrapes in-store receipt data from www.esselunga.it/area-utenti (the Fidaty card
area), NOT from spesaonline.esselunga.it.

The shoppingMovements page is an AngularJS SPA. After login, the receipt data
is available in the Angular scope as `ctrl.shoppingMovements`. Each movement
contains: id, descrizioneCommerciale, dataOperazione, importo, nomeFile.

Individual item details are only available as PDFs — we store the summary
(date, total, store) as orders, and can optionally download PDFs later.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.scrapers.order_scraper_base import Order, OrderItem, OrderScraperBase

logger = logging.getLogger(__name__)

AREA_UTENTI_URL = "https://www.esselunga.it/area-utenti/ist35/myesselunga/shoppingMovements"

# JS to extract receipt data from AngularJS scope
EXTRACT_MOVEMENTS_JS = """
() => {
    try {
        const el = document.getElementById("wrapper");
        if (!el) return { error: "wrapper not found" };
        const scope = angular.element(el).scope();
        if (!scope || !scope.ctrl) return { error: "angular scope not found" };
        const ctrl = scope.ctrl;

        // Set max results high and trigger reload
        ctrl.maxResults = 1000000000;

        const movements = ctrl.shoppingMovements || [];
        return {
            ok: true,
            currentCard: ctrl.currentCard || null,
            count: movements.length,
            movements: movements.map(m => ({
                id: m.id || null,
                descrizione: m.descrizioneCommerciale || m.descrizione || "",
                data: m.dataOperazione || "",
                importo: m.importo || null,
                nomeFile: m.nomeFile || null,
                tipo: m.tipoOperazione || m.tipo || "",
            }))
        };
    } catch (e) {
        return { error: e.message };
    }
}
"""

# JS to select "3 months" period and wait for data to load
SET_PERIOD_JS = """
async () => {
    try {
        const el = document.getElementById("wrapper");
        if (!el) return { error: "wrapper not found" };
        const scope = angular.element(el).scope();
        if (!scope || !scope.ctrl) return { error: "angular scope not found" };
        const ctrl = scope.ctrl;

        // Set to 3 months (value "number:2" = ultimi 3 mesi)
        const monthsBefore = document.getElementById("monthsBefore");
        if (monthsBefore) {
            monthsBefore.value = "number:2";
            monthsBefore.dispatchEvent(new Event("change"));
        }

        // Set high max results
        ctrl.maxResults = 1000000000;

        // Wait for Angular to digest
        await new Promise(r => setTimeout(r, 3000));

        return { ok: true };
    } catch (e) {
        return { error: e.message };
    }
}
"""


class EsselungaOrderScraper(OrderScraperBase):
    """Scrape receipt history from Esselunga Area Utenti."""

    chain_slug = "esselunga"

    def __init__(self) -> None:
        self._page = None
        self._browser = None
        self._context = None
        self._playwright = None
        self._logged_in = False

    async def login_with_session(self, session_data: dict) -> bool:
        """Log in using a saved Playwright storageState (cookies + localStorage)."""
        try:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            )
            self._context = await self._browser.new_context(
                viewport={"width": 1280, "height": 720},
                locale="it-IT",
                timezone_id="Europe/Rome",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            self._context.set_default_timeout(30000)

            # Load cookies from session
            cookies = session_data.get("cookies", [])
            if cookies:
                await self._context.add_cookies(cookies)

            # Load localStorage if present
            origins = session_data.get("origins", [])
            if origins:
                await self._context.add_init_script(
                    f"(() => {{ const data = {json.dumps(origins)}; "
                    "data.forEach(o => o.localStorage.forEach(i => "
                    "window.localStorage.setItem(i.name, i.value))); }})()"
                )

            self._page = await self._context.new_page()

            # Navigate to shoppingMovements
            logger.info("Esselunga: loading area utenti with saved session...")
            try:
                await self._page.goto(
                    AREA_UTENTI_URL,
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
            except Exception:
                pass
            await self._page.wait_for_timeout(5000)

            # Check if we're on the right page (not redirected to login)
            url = self._page.url
            if "shoppingMovements" in url and "login" not in url.lower():
                self._logged_in = True
                logger.info("Esselunga: session login successful (on shoppingMovements page).")
                return True
            else:
                logger.warning("Esselunga: session expired — redirected to %s", url)
                return False

        except Exception:
            logger.exception("Esselunga: session login failed.")
            return False

    async def login(self, email: str, password: str) -> bool:
        """Log in via Playwright — not typically used since we use remote browser login."""
        # The remote browser login handles authentication.
        # This is kept as a stub for the interface.
        logger.warning("Esselunga: email/password login not supported for area-utenti. Use remote browser login.")
        return False

    async def fetch_orders(self, since: datetime | None = None) -> list[Order]:
        """Extract shopping movements from the AngularJS scope."""
        if not self._logged_in or not self._page:
            logger.error("Esselunga: not logged in.")
            return []

        # Set period to 3 months
        logger.info("Esselunga: setting period to 3 months...")
        period_result = await self._page.evaluate(SET_PERIOD_JS)
        if period_result and period_result.get("error"):
            logger.warning("Esselunga: failed to set period: %s", period_result["error"])
            # Continue anyway — default period might still have data

        # Wait for data to load
        await self._page.wait_for_timeout(3000)

        # Extract movements from Angular scope
        logger.info("Esselunga: extracting shopping movements from Angular scope...")
        result = await self._page.evaluate(EXTRACT_MOVEMENTS_JS)

        if not result or result.get("error"):
            logger.error("Esselunga: failed to extract movements: %s", result)
            return []

        logger.info(
            "Esselunga: found %d movements (card: %s)",
            result.get("count", 0),
            result.get("currentCard"),
        )

        movements = result.get("movements", [])
        orders: list[Order] = []

        for m in movements:
            try:
                order = self._parse_movement(m)
                if order and (since is None or order.order_date >= since):
                    orders.append(order)
            except Exception:
                logger.exception("Esselunga: failed to parse movement: %s", str(m)[:200])

        logger.info("Esselunga: returning %d orders (filtered by since=%s).", len(orders), since)
        return orders

    @staticmethod
    def _parse_movement(raw: dict[str, Any]) -> Order | None:
        """Parse a raw movement dict into an Order."""
        movement_id = raw.get("id")
        if not movement_id:
            nome_file = raw.get("nomeFile")
            if nome_file:
                movement_id = nome_file
            else:
                return None

        movement_id = str(movement_id)

        # Parse date — format is typically "dd/MM/yyyy" or "yyyy-MM-dd"
        date_str = raw.get("data", "")
        order_date = None
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y %H:%M:%S"):
            try:
                order_date = datetime.strptime(str(date_str), fmt)
                break
            except (ValueError, TypeError):
                continue
        if order_date is None:
            order_date = datetime.now()

        # Parse amount
        total = None
        importo = raw.get("importo")
        if importo is not None:
            try:
                # Italian format: "12,34" or "12.34"
                total = Decimal(str(importo).replace(",", "."))
            except (InvalidOperation, ValueError):
                pass

        # Store name from descrizioneCommerciale
        store_name = raw.get("descrizione", "").strip() or None

        return Order(
            external_order_id=movement_id,
            order_date=order_date,
            total_amount=total,
            store_name=store_name,
            status="completed",
            items=[],  # Items are only in the PDF — not available in the list
            raw_data=raw,
        )

    async def get_storage_state(self) -> dict | None:
        """Return Playwright storageState after a successful login."""
        if self._context and self._logged_in:
            return await self._context.storage_state()
        return None

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
