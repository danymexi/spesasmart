"""Remote browser login via screenshot streaming.

Launches a Playwright headless browser, navigates to the supermarket login page,
and streams screenshots to the frontend. The user interacts by clicking on the
screenshot image and typing via a text input — events are forwarded to the
server-side browser. When the login succeeds, the session (cookies) is captured,
encrypted, and saved to the DB.
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models.purchase import SupermarketCredential
from app.models.user import UserProfile
from app.services.credential_encryption import encrypt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/supermarket-login", tags=["remote-login"])

SUPPORTED_CHAINS = {"esselunga", "iperal"}
MAX_SESSIONS = 2
SESSION_TIMEOUT_SECONDS = 300  # 5 minutes

LOGIN_URLS: dict[str, str] = {
    "iperal": "https://www.iperalspesaonline.it",
    "esselunga": "https://www.esselunga.it/area-utenti/ist35/myesselunga/shoppingMovements",
}

# JavaScript to remove headless browser fingerprints
STEALTH_JS = """
// Remove navigator.webdriver flag
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// Override permissions query
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) =>
    parameters.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : originalQuery(parameters);

// Override plugins to look like a real browser
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5],
});

// Override languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['it-IT', 'it', 'en-US', 'en'],
});

// Chrome runtime mock
window.chrome = { runtime: {} };
"""

VIEWPORT_DEFAULT = {"width": 1280, "height": 720}
MOBILE_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
DESKTOP_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


# ── Session management ──────────────────────────────────────────────────────

@dataclass
class LoginSession:
    session_id: str
    user_id: uuid.UUID
    chain_slug: str
    playwright: Any = None
    browser: Any = None
    context: Any = None
    page: Any = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "waiting"  # "waiting" | "success" | "error"
    error_message: str | None = None
    _auth_task: Any = None


active_sessions: dict[str, LoginSession] = {}
_cleanup_task: asyncio.Task | None = None


def _ensure_cleanup_task() -> None:
    """Start the background cleanup loop if not already running."""
    global _cleanup_task
    if _cleanup_task is None or _cleanup_task.done():
        _cleanup_task = asyncio.create_task(_cleanup_loop())


async def _cleanup_loop() -> None:
    """Close sessions older than SESSION_TIMEOUT_SECONDS."""
    while True:
        await asyncio.sleep(30)
        now = datetime.now(timezone.utc)
        expired = [
            sid
            for sid, sess in active_sessions.items()
            if (now - sess.created_at).total_seconds() > SESSION_TIMEOUT_SECONDS
        ]
        for sid in expired:
            logger.info("Auto-closing expired session %s", sid)
            await _close_session(sid)


async def _close_session(session_id: str) -> None:
    """Safely close a login session and release Playwright resources."""
    sess = active_sessions.pop(session_id, None)
    if sess is None:
        return
    if sess._auth_task and not sess._auth_task.done():
        sess._auth_task.cancel()
    try:
        if sess.context:
            await sess.context.close()
        if sess.browser:
            await sess.browser.close()
        if sess.playwright:
            await sess.playwright.stop()
    except Exception:
        logger.exception("Error closing session %s", session_id)


# ── Auth detection ───────────────────────────────────────────────────────────

async def _check_auth_loop(session_id: str) -> None:
    """Background task that polls the page to detect successful login."""
    while session_id in active_sessions:
        sess = active_sessions.get(session_id)
        if sess is None or sess.status != "waiting":
            return

        try:
            if sess.chain_slug == "iperal":
                result = await sess.page.evaluate("""
                    async () => {
                        try {
                            const r = await fetch('/ebsn/api/auth/test');
                            const d = await r.json();
                            return d.user?.userId > 0;
                        } catch { return false; }
                    }
                """)
            elif sess.chain_slug == "esselunga":
                # Check if we're on the shoppingMovements page (logged in)
                result = await sess.page.evaluate("""
                    () => {
                        try {
                            // If we can see the page content (not a login redirect), we're logged in
                            const url = window.location.href;
                            return url.includes('shoppingMovements') && !url.includes('login');
                        } catch { return false; }
                    }
                """)
            else:
                result = False

            if result:
                logger.info("Auth detected for session %s (%s)", session_id, sess.chain_slug)
                sess.status = "success"
                # Capture and save session
                await _save_session(sess)
                return

        except Exception:
            # Page might be navigating, ignore errors
            pass

        await asyncio.sleep(3)


async def _save_session(sess: LoginSession) -> None:
    """Capture browser storage state, encrypt, and save to DB."""
    try:
        storage_state = await sess.context.storage_state()
        encrypted_session = encrypt(json.dumps(storage_state))

        from app.database import async_session

        async with async_session() as db:
            result = await db.execute(
                select(SupermarketCredential).where(
                    SupermarketCredential.user_id == sess.user_id,
                    SupermarketCredential.chain_slug == sess.chain_slug,
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.encrypted_session = encrypted_session
                existing.is_valid = True
                existing.last_error = None
                existing.updated_at = datetime.now(timezone.utc)
            else:
                cred = SupermarketCredential(
                    user_id=sess.user_id,
                    chain_slug=sess.chain_slug,
                    encrypted_session=encrypted_session,
                )
                db.add(cred)

            await db.commit()

        logger.info("Session saved for user=%s chain=%s", sess.user_id, sess.chain_slug)

        # Trigger sync in background
        asyncio.create_task(_trigger_sync(sess.user_id, sess.chain_slug))

    except Exception:
        logger.exception("Failed to save session for %s", sess.session_id)
        sess.status = "error"
        sess.error_message = "Impossibile salvare la sessione."


async def _trigger_sync(user_id: uuid.UUID, chain_slug: str) -> None:
    """Trigger purchase sync after successful login."""
    try:
        from app.services.purchase_sync import PurchaseSyncService
        await PurchaseSyncService.sync_user_chain(user_id, chain_slug)
    except Exception:
        logger.exception("Post-login sync failed for user=%s chain=%s", user_id, chain_slug)


# ── Schemas ──────────────────────────────────────────────────────────────────

class StartRequest(BaseModel):
    viewport_width: int = 1280
    viewport_height: int = 720


class StartResponse(BaseModel):
    session_id: str
    viewport_width: int
    viewport_height: int


class ActionRequest(BaseModel):
    type: str  # "click" | "type" | "press"
    x: float | None = None
    y: float | None = None
    text: str | None = None
    key: str | None = None


class StatusResponse(BaseModel):
    status: str  # "waiting" | "success" | "error"
    error: str | None = None


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/{chain_slug}/start", response_model=StartResponse)
async def start_remote_login(
    chain_slug: str,
    body: StartRequest | None = None,
    user: UserProfile = Depends(get_current_user),
):
    """Start a remote browser session for supermarket login."""
    if chain_slug not in SUPPORTED_CHAINS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Catena non supportata: {chain_slug}",
        )

    # Check max concurrent sessions
    if len(active_sessions) >= MAX_SESSIONS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Troppe sessioni di login attive. Riprova tra qualche minuto.",
        )

    # Close any existing session for this user+chain
    for sid, sess in list(active_sessions.items()):
        if sess.user_id == user.id and sess.chain_slug == chain_slug:
            await _close_session(sid)

    # Determine viewport and user agent
    vw = body.viewport_width if body else 1280
    vh = body.viewport_height if body else 720
    # Clamp to reasonable bounds
    vw = max(320, min(vw, 1920))
    vh = max(480, min(vh, 1200))
    is_mobile = vw < 768
    user_agent = MOBILE_USER_AGENT if is_mobile else DESKTOP_USER_AGENT

    session_id = str(uuid.uuid4())

    try:
        from playwright.async_api import async_playwright

        pw = await async_playwright().start()
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--no-sandbox",
            ],
        )
        context = await browser.new_context(
            viewport={"width": vw, "height": vh},
            locale="it-IT",
            user_agent=user_agent,
            is_mobile=is_mobile,
            has_touch=is_mobile,
        )

        # Inject stealth script before any page loads
        await context.add_init_script(STEALTH_JS)

        page = await context.new_page()

        url = LOGIN_URLS[chain_slug]
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)

    except Exception as e:
        logger.exception("Failed to start browser for session %s", session_id)
        # Clean up on failure
        try:
            if "context" in dir() and context:
                await context.close()
            if "browser" in dir() and browser:
                await browser.close()
            if "pw" in dir() and pw:
                await pw.stop()
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Impossibile avviare il browser: {e}",
        )

    sess = LoginSession(
        session_id=session_id,
        user_id=user.id,
        chain_slug=chain_slug,
        playwright=pw,
        browser=browser,
        context=context,
        page=page,
    )
    active_sessions[session_id] = sess

    # Start auth detection loop
    sess._auth_task = asyncio.create_task(_check_auth_loop(session_id))

    # Ensure cleanup task is running
    _ensure_cleanup_task()

    logger.info("Started remote login session %s for user=%s chain=%s (viewport=%dx%d)", session_id, user.id, chain_slug, vw, vh)
    return StartResponse(session_id=session_id, viewport_width=vw, viewport_height=vh)


@router.get("/{session_id}/screenshot")
async def get_screenshot(
    session_id: str,
    user: UserProfile = Depends(get_current_user),
):
    """Return a JPEG screenshot of the remote browser."""
    sess = active_sessions.get(session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Sessione non trovata.")
    if sess.user_id != user.id:
        raise HTTPException(status_code=403, detail="Non autorizzato.")

    try:
        image_bytes = await sess.page.screenshot(type="jpeg", quality=70)
    except Exception as e:
        logger.exception("Screenshot failed for session %s", session_id)
        raise HTTPException(status_code=500, detail=f"Screenshot fallito: {e}")

    return Response(
        content=image_bytes,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )


@router.post("/{session_id}/action")
async def send_action(
    session_id: str,
    body: ActionRequest,
    user: UserProfile = Depends(get_current_user),
):
    """Send a mouse click, key press, or text input to the remote browser."""
    sess = active_sessions.get(session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Sessione non trovata.")
    if sess.user_id != user.id:
        raise HTTPException(status_code=403, detail="Non autorizzato.")

    try:
        if body.type == "click" and body.x is not None and body.y is not None:
            await sess.page.mouse.click(body.x, body.y)
        elif body.type == "type" and body.text is not None:
            await sess.page.keyboard.type(body.text)
        elif body.type == "press" and body.key is not None:
            await sess.page.keyboard.press(body.key)
        elif body.type == "scroll" and body.y is not None:
            await sess.page.mouse.wheel(body.x or 0, body.y)
        else:
            raise HTTPException(status_code=400, detail="Azione non valida.")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Action failed for session %s", session_id)
        raise HTTPException(status_code=500, detail=f"Azione fallita: {e}")

    return {"ok": True}


@router.get("/{session_id}/status", response_model=StatusResponse)
async def get_status(
    session_id: str,
    user: UserProfile = Depends(get_current_user),
):
    """Check the login status of the remote browser session."""
    sess = active_sessions.get(session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Sessione non trovata.")
    if sess.user_id != user.id:
        raise HTTPException(status_code=403, detail="Non autorizzato.")

    return StatusResponse(status=sess.status, error=sess.error_message)


@router.delete("/{session_id}")
async def cancel_session(
    session_id: str,
    user: UserProfile = Depends(get_current_user),
):
    """Cancel and close a remote login session."""
    sess = active_sessions.get(session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Sessione non trovata.")
    if sess.user_id != user.id:
        raise HTTPException(status_code=403, detail="Non autorizzato.")

    await _close_session(session_id)
    return {"detail": "Sessione chiusa."}
