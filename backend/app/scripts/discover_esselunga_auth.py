"""Esselunga Spesa Online — auth & orders API discovery.

Opens a VISIBLE browser so you can log in manually to spesaonline.esselunga.it.
Intercepts all network requests during login and while navigating to "I miei ordini"
to discover the authentication and order-history API endpoints.

Usage:
    cd ~/spesasmart/backend
    PYTHONPATH=. python -m app.scripts.discover_esselunga_auth
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

SITE_URL = "https://spesaonline.esselunga.it"
OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "data"
OUTPUT_FILE = OUTPUT_DIR / "esselunga_api_discovery.json"


async def run() -> None:
    from playwright.async_api import async_playwright

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    captured_requests: list[dict] = []

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=False)
    context = await browser.new_context(
        viewport={"width": 1280, "height": 900},
        locale="it-IT",
        timezone_id="Europe/Rome",
    )
    page = await context.new_page()

    # Intercept all requests
    async def on_request(request):
        url = request.url
        # Filter for API-like requests (skip static assets)
        if any(ext in url for ext in [".js", ".css", ".png", ".jpg", ".svg", ".woff", ".ico"]):
            return
        entry = {
            "timestamp": datetime.now().isoformat(),
            "method": request.method,
            "url": url,
            "headers": dict(request.headers),
        }
        if request.post_data:
            try:
                entry["post_data"] = json.loads(request.post_data)
            except (json.JSONDecodeError, TypeError):
                entry["post_data"] = request.post_data[:500]
        captured_requests.append(entry)
        logger.info("%s %s", request.method, url[:120])

    async def on_response(response):
        url = response.url
        # Capture response details for auth/order endpoints
        if any(kw in url.lower() for kw in [
            "login", "auth", "token", "session", "order", "ordini",
            "storico", "history", "account", "profile", "user",
        ]):
            try:
                body = await response.text()
                # Truncate large responses
                if len(body) > 5000:
                    body = body[:5000] + "...[truncated]"
                logger.info("RESPONSE %d %s => %s", response.status, url[:100], body[:200])
                # Append response info to the last matching request
                for req in reversed(captured_requests):
                    if req["url"] == url:
                        req["response_status"] = response.status
                        req["response_body_preview"] = body[:2000]
                        break
            except Exception:
                pass

    page.on("request", on_request)
    page.on("response", on_response)

    # Navigate to Esselunga
    logger.info("Navigating to %s ...", SITE_URL)
    try:
        await page.goto(f"{SITE_URL}/commerce/nav/supermercato/store/home",
                        wait_until="domcontentloaded", timeout=60_000)
    except Exception:
        pass
    await page.wait_for_timeout(3000)

    # Accept cookies if present
    try:
        btn = page.locator("button:has-text('Accetta tutti')").first
        if await btn.is_visible(timeout=3000):
            await btn.click()
            await page.wait_for_timeout(1000)
    except Exception:
        pass

    logger.info("")
    logger.info("=" * 60)
    logger.info("STEP 1: Log in to Esselunga Spesa Online")
    logger.info("Use the browser window to log in with your credentials.")
    logger.info("After login, navigate to 'I miei ordini' / order history.")
    logger.info("Waiting up to 10 minutes...")
    logger.info("=" * 60)

    # Wait for user to log in and browse orders (10 min timeout)
    # Poll: check if URL contains something indicating orders page
    for _ in range(200):  # 200 * 3s = 10 min
        await asyncio.sleep(3)
        current_url = page.url
        # Check if we see order-related URL patterns
        if any(kw in current_url.lower() for kw in ["order", "ordini", "storico"]):
            logger.info("Detected order page URL: %s", current_url)
            await asyncio.sleep(5)  # Let requests settle
            break

    logger.info("")
    logger.info("=" * 60)
    logger.info("STEP 2: Saving captured requests...")
    logger.info("=" * 60)

    # Filter interesting requests
    auth_requests = [r for r in captured_requests if any(
        kw in r["url"].lower() for kw in [
            "login", "auth", "token", "session", "oauth", "sso",
        ]
    )]
    order_requests = [r for r in captured_requests if any(
        kw in r["url"].lower() for kw in [
            "order", "ordini", "storico", "history", "purchase",
        ]
    )]

    result = {
        "discovery_date": datetime.now().isoformat(),
        "total_requests_captured": len(captured_requests),
        "auth_requests": auth_requests,
        "order_requests": order_requests,
        "all_api_requests": [
            r for r in captured_requests
            if "/commerce/" in r["url"] or "/api/" in r["url"]
        ],
    }

    OUTPUT_FILE.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str))

    logger.info("Saved %d total requests to %s", len(captured_requests), OUTPUT_FILE)
    logger.info("  - Auth-related: %d", len(auth_requests))
    logger.info("  - Order-related: %d", len(order_requests))
    logger.info("")

    # Print summary of interesting endpoints
    if auth_requests:
        logger.info("AUTH ENDPOINTS FOUND:")
        for r in auth_requests:
            logger.info("  %s %s", r["method"], r["url"][:150])
    if order_requests:
        logger.info("ORDER ENDPOINTS FOUND:")
        for r in order_requests:
            logger.info("  %s %s", r["method"], r["url"][:150])

    await browser.close()
    await pw.stop()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
