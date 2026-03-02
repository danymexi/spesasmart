"""Iperal Spesa Online — manual login helper.

Opens a visible (non-headless) Chromium browser so the user can log in to
iperalspesaonline.it (bypassing reCAPTCHA manually).

Once login is confirmed the Playwright storageState (cookies + localStorage)
is saved to a JSON file that IperalOnlineScraper can load via httpx.

Note: store/warehouse selection is NOT required — the authenticated API
returns products with prices regardless.

Usage:
    cd ~/spesasmart/backend
    PYTHONPATH=. python -m app.scrapers.iperal_session_helper
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

SITE_URL = "https://www.iperalspesaonline.it"
AUTH_TEST_URL = f"{SITE_URL}/ebsn/api/auth/test"

DEFAULT_SESSION_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "iperal_session.json"


async def _poll_auth(page, timeout_s: int = 300) -> bool:
    """Poll /ebsn/api/auth/test until userId > 0 or timeout."""
    for _ in range(timeout_s // 3):
        try:
            result = await page.evaluate(f"""async () => {{
                try {{
                    const r = await fetch("{AUTH_TEST_URL}", {{
                        credentials: "include",
                        headers: {{"Accept": "application/json"}},
                    }});
                    const d = await r.json();
                    return d?.data?.user?.userId ?? d?.user?.userId ?? 0;
                }} catch (e) {{ return 0; }}
            }}""")
            if result and int(result) > 0:
                return True
        except Exception:
            pass
        await asyncio.sleep(3)
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

    # Load session from previous run if available (speeds up re-login)
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

    # ---- Wait for login ----
    logger.info("")
    logger.info("=== Log in to Iperal Spesa Online ===")
    logger.info("Please log in using the browser window.")
    logger.info("Waiting for successful authentication (up to 5 min)...")

    if await _poll_auth(page):
        logger.info("Login confirmed!")
    else:
        logger.error("Login not detected within timeout. Saving partial session anyway.")

    # ---- Save session ----
    state = await context.storage_state()
    dest.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    logger.info("")
    logger.info("Session saved to: %s", dest)
    logger.info("You can now close the browser.")

    await browser.close()
    await pw.stop()


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    asyncio.run(run(path))


if __name__ == "__main__":
    main()
