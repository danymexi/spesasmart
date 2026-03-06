"""Esselunga Spesa Online — manual login session helper.

Opens a visible (non-headless) Chromium browser so the user can log in to
spesaonline.esselunga.it using any method (Google, passkey, Face ID, email/password).

Once login is confirmed the Playwright storageState (cookies + localStorage)
is saved to a JSON file and optionally uploaded to the backend API.

Usage:
    cd ~/spesasmart/backend
    PYTHONPATH=. python -m app.scripts.esselunga_session_helper
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

import httpx

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

SITE_URL = "https://spesaonline.esselunga.it"
SESSION_CHECK_URL = f"{SITE_URL}/commerce/resources/nav/supermercato"

DEFAULT_SESSION_PATH = (
    Path(__file__).resolve().parent.parent.parent / "data" / "esselunga_session.json"
)

BACKEND_BASE = "http://localhost:8000/api/v1"


async def _poll_auth(page, timeout_s: int = 300) -> bool:
    """Poll the Esselunga session endpoint until authenticated or timeout."""
    for _ in range(timeout_s // 3):
        try:
            result = await page.evaluate(f"""async () => {{
                try {{
                    const r = await fetch("{SESSION_CHECK_URL}", {{
                        credentials: "include",
                        headers: {{"Accept": "application/json"}},
                    }});
                    if (!r.ok) return {{ ok: false, status: r.status }};
                    const d = await r.json();
                    // A successful response with store data means logged in
                    return {{ ok: true, data: d }};
                }} catch (e) {{ return {{ ok: false, error: e.message }}; }}
            }}""")
            if result and result.get("ok"):
                return True
        except Exception:
            pass
        await asyncio.sleep(3)
    return False


async def _upload_session(session_path: Path) -> bool:
    """Upload the session to the backend API."""
    try:
        session_data = json.loads(session_path.read_text())
    except Exception as e:
        logger.error("Cannot read session file: %s", e)
        return False

    # Ask for JWT token
    print()
    print("Per caricare la sessione nel backend, serve il tuo JWT token.")
    print("Puoi ottenerlo dalla app (localStorage) o dall'endpoint /auth/login.")
    token = input("JWT token (invio per saltare): ").strip()
    if not token:
        logger.info("Upload saltato. Puoi caricare la sessione manualmente via API.")
        return False

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{BACKEND_BASE}/users/me/supermarket-accounts/esselunga/session",
                json=session_data,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
            )
            if resp.status_code == 200:
                logger.info("Sessione caricata nel backend!")
                return True
            else:
                logger.error(
                    "Upload fallito (status %d): %s",
                    resp.status_code,
                    resp.text[:300],
                )
                return False
    except Exception as e:
        logger.error("Errore nell'upload: %s", e)
        return False


async def run(session_path: Path | None = None) -> None:
    """Main helper flow."""
    from playwright.async_api import async_playwright

    dest = session_path or DEFAULT_SESSION_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Launching visible browser...")
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=False)
    context = await browser.new_context(
        viewport={"width": 1280, "height": 900},
        locale="it-IT",
        timezone_id="Europe/Rome",
    )
    page = await context.new_page()

    # Load session from previous run if available
    if dest.exists():
        logger.info("Found existing session file — loading cookies...")
        try:
            state = json.loads(dest.read_text())
            await context.add_cookies(state.get("cookies", []))
        except Exception:
            logger.warning("Could not load previous session; starting fresh.")

    logger.info("Navigating to %s ...", SITE_URL)
    await page.goto(SITE_URL, wait_until="domcontentloaded", timeout=60_000)
    await page.wait_for_timeout(3000)

    # Accept cookies banner if present
    try:
        btn = page.locator("button:has-text('Accetta tutti')").first
        if await btn.is_visible(timeout=3000):
            await btn.click()
            await page.wait_for_timeout(1000)
    except Exception:
        pass

    # ---- Wait for login ----
    logger.info("")
    logger.info("=== Accedi a Esselunga Spesa Online ===")
    logger.info("Usa il browser per fare login (Google, passkey, email/password, ecc.)")
    logger.info("In attesa dell'autenticazione (max 5 min)...")

    if await _poll_auth(page):
        logger.info("Login confermato!")
    else:
        logger.error("Login non rilevato entro il timeout. Salvataggio sessione parziale.")

    # ---- Save session ----
    state = await context.storage_state()
    dest.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    logger.info("")
    logger.info("Sessione salvata in: %s", dest)

    # ---- Try to discover order endpoints ----
    logger.info("")
    logger.info("Navigazione a 'I miei ordini' per scoprire gli endpoint...")
    order_urls = [
        f"{SITE_URL}/commerce/nav/supermercato/store/acquisti",
        f"{SITE_URL}/commerce/nav/supermercato/store/ordini",
        f"{SITE_URL}/commerce/nav/supermercato/store/account/ordini",
    ]

    api_calls: list[str] = []

    async def on_request(request):
        url = request.url
        if "/commerce/resources/" in url and not any(
            ext in url for ext in [".js", ".css", ".png", ".jpg", ".svg", ".woff"]
        ):
            api_calls.append(f"{request.method} {url}")
            logger.info("  API: %s %s", request.method, url[:120])

    page.on("request", on_request)

    for url in order_urls:
        try:
            logger.info("Trying %s ...", url)
            await page.goto(url, wait_until="domcontentloaded", timeout=15_000)
            await page.wait_for_timeout(3000)
        except Exception:
            continue

    if api_calls:
        logger.info("")
        logger.info("API calls intercepted:")
        for call in api_calls:
            logger.info("  %s", call)

    await browser.close()
    await pw.stop()

    # ---- Upload to backend ----
    logger.info("")
    await _upload_session(dest)

    logger.info("")
    logger.info("Fatto! Puoi chiudere questo terminale.")


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    asyncio.run(run(path))


if __name__ == "__main__":
    main()
