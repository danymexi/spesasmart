"""Web Push subscription endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.config import Settings, get_settings
from app.services.web_push_sender import send_web_push

router = APIRouter(prefix="/web-push", tags=["web-push"])

# ── In-memory store (replace with DB in production) ──────────────────────────
# key: user_id, value: subscription JSON dict
_subscriptions: dict[str, dict] = {}


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
async def subscribe(req: SubscribeRequest):
    """Save a Web Push subscription for a user."""
    _subscriptions[req.user_id] = req.subscription.model_dump()
    return {"status": "subscribed", "user_id": req.user_id}


@router.delete("/subscribe/{user_id}")
async def unsubscribe(user_id: str):
    """Remove a Web Push subscription."""
    _subscriptions.pop(user_id, None)
    return {"status": "unsubscribed", "user_id": user_id}


@router.post("/send")
async def send_push(
    req: PushMessageRequest,
    settings: Settings = Depends(get_settings),
):
    """Send a push notification to a specific user (for testing/admin)."""
    subscription = _subscriptions.get(req.user_id)
    if not subscription:
        raise HTTPException(status_code=404, detail="No subscription for this user")

    payload = {"title": req.title, "body": req.body}
    if req.data:
        payload.update(req.data)

    ok = send_web_push(subscription, payload, settings)
    if not ok:
        raise HTTPException(status_code=500, detail="Push delivery failed")

    return {"status": "sent", "user_id": req.user_id}


def get_all_subscriptions() -> dict[str, dict]:
    """Access subscriptions from other modules (e.g., notification service)."""
    return _subscriptions
