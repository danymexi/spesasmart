"""Web Push subscription endpoints (DB-backed)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_db
from app.models.user import WebPushSubscription
from app.services.web_push_sender import send_web_push

router = APIRouter(prefix="/web-push", tags=["web-push"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class SubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscription(BaseModel):
    endpoint: str
    keys: SubscriptionKeys
    expirationTime: float | None = None


class SubscribeRequest(BaseModel):
    user_id: str
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
async def subscribe(req: SubscribeRequest, db: AsyncSession = Depends(get_db)):
    """Save or update a Web Push subscription for a user."""
    # Upsert: if endpoint already exists, update keys and user
    existing = await db.execute(
        select(WebPushSubscription).where(
            WebPushSubscription.endpoint == req.subscription.endpoint
        )
    )
    sub = existing.scalar_one_or_none()

    if sub:
        sub.user_id = req.user_id
        sub.p256dh = req.subscription.keys.p256dh
        sub.auth = req.subscription.keys.auth
    else:
        sub = WebPushSubscription(
            user_id=req.user_id,
            endpoint=req.subscription.endpoint,
            p256dh=req.subscription.keys.p256dh,
            auth=req.subscription.keys.auth,
        )
        db.add(sub)

    await db.flush()
    return {"status": "subscribed", "user_id": req.user_id}


@router.delete("/subscribe/{user_id}")
async def unsubscribe(user_id: str, db: AsyncSession = Depends(get_db)):
    """Remove all Web Push subscriptions for a user."""
    await db.execute(
        delete(WebPushSubscription).where(WebPushSubscription.user_id == user_id)
    )
    return {"status": "unsubscribed", "user_id": user_id}


@router.post("/send")
async def send_push(
    req: PushMessageRequest,
    settings: Settings = Depends(get_settings),
    db: AsyncSession = Depends(get_db),
):
    """Send a push notification to a specific user (for testing/admin)."""
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
