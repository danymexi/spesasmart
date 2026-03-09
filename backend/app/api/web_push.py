"""Web Push subscription endpoints (DB-backed)."""

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import Settings, get_settings
from app.database import get_db
from app.models.user import UserProfile, WebPushSubscription
from app.services.web_push_sender import send_web_push

router = APIRouter(prefix="/web-push", tags=["web-push"])


# ── Admin key dependency ─────────────────────────────────────────────────────

async def require_admin_key(x_admin_key: str = Header(...)):
    settings = get_settings()
    if not settings.admin_api_key or x_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=403, detail="Invalid or missing admin API key")
    return True


# ── Schemas ──────────────────────────────────────────────────────────────────

class SubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscription(BaseModel):
    endpoint: str
    keys: SubscriptionKeys
    expirationTime: float | None = None


class SubscribeRequest(BaseModel):
    subscription: PushSubscription


class PushMessageRequest(BaseModel):
    user_id: str
    title: str
    body: str
    data: dict | None = None


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/vapid-key")
async def get_vapid_public_key(settings: Settings = Depends(get_settings)):
    """Return the VAPID public key for the client to subscribe."""
    if not settings.vapid_public_key:
        raise HTTPException(status_code=503, detail="VAPID keys not configured")
    return {"public_key": settings.vapid_public_key}


@router.post("/subscribe")
async def subscribe(
    req: SubscribeRequest,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save or update a Web Push subscription for the authenticated user."""
    existing = await db.execute(
        select(WebPushSubscription).where(
            WebPushSubscription.endpoint == req.subscription.endpoint
        )
    )
    sub = existing.scalar_one_or_none()

    if sub:
        sub.user_id = user.id
        sub.p256dh = req.subscription.keys.p256dh
        sub.auth = req.subscription.keys.auth
    else:
        sub = WebPushSubscription(
            user_id=user.id,
            endpoint=req.subscription.endpoint,
            p256dh=req.subscription.keys.p256dh,
            auth=req.subscription.keys.auth,
        )
        db.add(sub)

    await db.flush()
    return {"status": "subscribed", "user_id": str(user.id)}


@router.delete("/subscribe")
async def unsubscribe(
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove all Web Push subscriptions for the authenticated user."""
    await db.execute(
        delete(WebPushSubscription).where(WebPushSubscription.user_id == user.id)
    )
    return {"status": "unsubscribed", "user_id": str(user.id)}


@router.post("/send")
async def send_push(
    req: PushMessageRequest,
    _=Depends(require_admin_key),
    settings: Settings = Depends(get_settings),
    db: AsyncSession = Depends(get_db),
):
    """Send a push notification to a specific user (admin only)."""
    result = await db.execute(
        select(WebPushSubscription).where(WebPushSubscription.user_id == req.user_id)
    )
    subs = result.scalars().all()
    if not subs:
        raise HTTPException(status_code=404, detail="No subscription for this user")

    payload = {"title": req.title, "body": req.body}
    if req.data:
        payload.update(req.data)

    sent = 0
    expired_ids = []
    for sub in subs:
        sub_info = {
            "endpoint": sub.endpoint,
            "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
        }
        ok, is_expired = send_web_push(sub_info, payload, settings)
        if ok:
            sent += 1
        elif is_expired:
            expired_ids.append(sub.id)

    # Clean up expired subscriptions
    if expired_ids:
        await db.execute(
            delete(WebPushSubscription).where(WebPushSubscription.id.in_(expired_ids))
        )

    if sent == 0:
        raise HTTPException(status_code=500, detail="Push delivery failed")

    return {"status": "sent", "user_id": req.user_id, "sent_count": sent}
