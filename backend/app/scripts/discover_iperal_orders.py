"""Iperal Spesa Online — order history API discovery.

Uses an existing authenticated session (from iperal_session_helper.py) to probe
potential order-history endpoints on iperalspesaonline.it.

Usage:
    cd ~/spesasmart/backend
    PYTHONPATH=. python -m app.scripts.discover_iperal_orders
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

import httpx

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "https://www.iperalspesaonline.it"
SESSION_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "iperal_session.json"
OUTPUT_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "iperal_orders_discovery.json"

# Candidate endpoints to probe (based on common e-commerce API patterns)
CANDIDATE_ENDPOINTS = [
    ("GET", "/ebsn/api/orders"),
    ("GET", "/ebsn/api/order/list"),
    ("GET", "/ebsn/api/order/history"),
    ("GET", "/ebsn/api/user/orders"),
    ("GET", "/ebsn/api/user/order/list"),
    ("GET", "/ebsn/api/auth/user/orders"),
    ("GET", "/ebsn/api/v1/orders"),
    ("GET", "/ebsn/api/purchase/history"),
    ("GET", "/ebsn/api/cart/history"),
    ("GET", "/ebsn/api/cart/orders"),
    ("GET", "/ebsn/api/cart/past"),
    ("POST", "/ebsn/api/orders"),
    ("POST", "/ebsn/api/order/list"),
    ("POST", "/ebsn/api/order/search"),
    # Additional patterns
    ("GET", "/ebsn/api/order"),
    ("GET", "/ebsn/api/orders/completed"),
    ("GET", "/ebsn/api/orders/past"),
    ("GET", "/ebsn/api/my-orders"),
    ("GET", "/ebsn/api/account/orders"),
]


async def run() -> None:
    if not SESSION_FILE.exists():
        logger.error("Session file not found: %s", SESSION_FILE)
        logger.error("Run iperal_session_helper.py first to create an authenticated session.")
        return

    # Load session cookies
    state = json.loads(SESSION_FILE.read_text())
    cookies_list = state.get("cookies", [])

    # Build cookie jar for httpx
    cookies = httpx.Cookies()
    for c in cookies_list:
        cookies.set(c["name"], c["value"], domain=c.get("domain", ""))

    results: list[dict] = []

    async with httpx.AsyncClient(
        base_url=BASE_URL,
        cookies=cookies,
        timeout=15.0,
        follow_redirects=True,
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": f"{BASE_URL}/",
        },
    ) as client:
        # First verify the session is still valid
        logger.info("Verifying session...")
        try:
            auth_resp = await client.get("/ebsn/api/auth/test")
            auth_data = auth_resp.json()
            user_id = (
                auth_data.get("data", {}).get("user", {}).get("userId")
                or auth_data.get("user", {}).get("userId")
                or 0
            )
            if not user_id or int(user_id) <= 0:
                logger.error("Session is not authenticated (userId=%s). Re-run iperal_session_helper.py.", user_id)
                logger.info("Auth test response: %s", json.dumps(auth_data, indent=2)[:500])
                return
            logger.info("Session valid! userId=%s", user_id)
        except Exception as e:
            logger.error("Failed to verify session: %s", e)
            return

        # Probe each candidate endpoint
        for method, path in CANDIDATE_ENDPOINTS:
            logger.info("Probing %s %s ...", method, path)
            try:
                if method == "GET":
                    resp = await client.get(path)
                else:
                    resp = await client.post(path, json={})

                body_text = resp.text[:3000]
                try:
                    body_json = resp.json()
                except Exception:
                    body_json = None

                entry = {
                    "method": method,
                    "path": path,
                    "status": resp.status_code,
                    "content_type": resp.headers.get("content-type", ""),
                    "body_preview": body_text[:1000],
                }

                # Highlight successful or interesting responses
                if resp.status_code == 200:
                    logger.info("  => 200 OK! Body: %s", body_text[:200])
                    entry["promising"] = True
                elif resp.status_code in (201, 204):
                    logger.info("  => %d (possibly valid)", resp.status_code)
                    entry["promising"] = True
                elif resp.status_code == 404:
                    logger.info("  => 404 Not Found")
                elif resp.status_code == 403:
                    logger.info("  => 403 Forbidden (endpoint exists but access denied)")
                    entry["promising"] = True
                else:
                    logger.info("  => %d", resp.status_code)

                results.append(entry)

            except Exception as e:
                logger.warning("  => Error: %s", e)
                results.append({
                    "method": method,
                    "path": path,
                    "error": str(e),
                })

            await asyncio.sleep(0.3)  # Be polite

    # Also try Playwright-based discovery (intercept XHR while navigating)
    logger.info("")
    logger.info("=" * 60)
    logger.info("Now launching browser to discover endpoints via navigation...")
    logger.info("=" * 60)

    try:
        from playwright.async_api import async_playwright

        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="it-IT",
            timezone_id="Europe/Rome",
            storage_state=str(SESSION_FILE),
        )
        page = await context.new_page()

        browser_requests: list[dict] = []

        async def on_request(request):
            url = request.url
            if any(ext in url for ext in [".js", ".css", ".png", ".jpg", ".svg", ".woff"]):
                return
            if "/ebsn/api/" in url or "/api/" in url:
                entry = {
                    "method": request.method,
                    "url": url,
                }
                if request.post_data:
                    try:
                        entry["post_data"] = json.loads(request.post_data)
                    except Exception:
                        entry["post_data"] = request.post_data[:500]
                browser_requests.append(entry)
                logger.info("  XHR: %s %s", request.method, url[:120])

        page.on("request", on_request)

        # Navigate to home, then try to find orders page
        await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_timeout(3000)

        # Try navigating to common order history URLs
        order_urls = [
            f"{BASE_URL}/ordini",
            f"{BASE_URL}/orders",
            f"{BASE_URL}/account/orders",
            f"{BASE_URL}/area-personale/ordini",
            f"{BASE_URL}/profilo/ordini",
        ]

        for url in order_urls:
            logger.info("Trying navigation to %s ...", url)
            try:
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=10_000)
                await page.wait_for_timeout(2000)
                if resp and resp.status == 200:
                    logger.info("  Page loaded! Checking for API calls...")
                    await page.wait_for_timeout(3000)
            except Exception:
                logger.info("  Navigation failed or timed out")

        # Look for order-related links on the page
        logger.info("")
        logger.info("Looking for order-related links on page...")
        try:
            links = await page.evaluate("""() => {
                const anchors = document.querySelectorAll('a');
                const results = [];
                for (const a of anchors) {
                    const href = a.href || '';
                    const text = a.textContent?.trim() || '';
                    if (href && (
                        href.toLowerCase().includes('order') ||
                        href.toLowerCase().includes('ordini') ||
                        href.toLowerCase().includes('storico') ||
                        text.toLowerCase().includes('ordini') ||
                        text.toLowerCase().includes('storico')
                    )) {
                        results.push({ href, text: text.substring(0, 100) });
                    }
                }
                return results;
            }""")
            if links:
                logger.info("Found %d order-related links:", len(links))
                for link in links:
                    logger.info("  %s => %s", link["text"], link["href"])
            else:
                logger.info("No order-related links found on current page.")
        except Exception:
            pass

        await browser.close()
        await pw.stop()

    except Exception as e:
        logger.warning("Browser discovery failed: %s", e)
        browser_requests = []

    # Save all results
    output = {
        "discovery_date": datetime.now().isoformat(),
        "session_file": str(SESSION_FILE),
        "api_probe_results": results,
        "promising_endpoints": [r for r in results if r.get("promising")],
        "browser_xhr_requests": browser_requests,
    }

    OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False, default=str))
    logger.info("")
    logger.info("Results saved to %s", OUTPUT_FILE)
    logger.info("Promising endpoints: %d", len(output["promising_endpoints"]))
    for ep in output["promising_endpoints"]:
        logger.info("  %s %s => %d", ep["method"], ep["path"], ep["status"])

    # Offer to upload session to backend
    await _upload_session()


BACKEND_BASE = "http://localhost:8000/api/v1"


async def _upload_session() -> None:
    """Upload the Iperal session to the backend API."""
    if not SESSION_FILE.exists():
        return

    print()
    print("Vuoi caricare la sessione nel backend?")
    token = input("JWT token (invio per saltare): ").strip()
    if not token:
        logger.info("Upload saltato.")
        return

    session_data = json.loads(SESSION_FILE.read_text())
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{BACKEND_BASE}/users/me/supermarket-accounts/iperal/session",
                json=session_data,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
            )
            if resp.status_code == 200:
                logger.info("Sessione Iperal caricata nel backend!")
            else:
                logger.error("Upload fallito (status %d): %s", resp.status_code, resp.text[:300])
    except Exception as e:
        logger.error("Errore nell'upload: %s", e)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
