"""Send Web Push notifications via pywebpush."""

import json
import logging

from pywebpush import webpush, WebPushException

from app.config import Settings

logger = logging.getLogger(__name__)


def send_web_push(
    subscription_info: dict,
    payload: dict,
    settings: Settings,
) -> tuple[bool, bool]:
    """
    Send a single web push notification.

    Returns:
        (success, is_expired) — True/False for each.
    """
    if not settings.vapid_private_key or not settings.vapid_public_key:
        logger.error("VAPID keys not configured — cannot send web push")
        return False, False

    try:
        webpush(
            subscription_info=subscription_info,
            data=json.dumps(payload),
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": settings.vapid_claims_email},
        )
        logger.info("Web push sent to %s", subscription_info.get("endpoint", "?")[:60])
        return True, False
    except WebPushException as ex:
        logger.error("Web push failed: %s", ex)
        if ex.response and ex.response.status_code in (404, 410):
            logger.warning("Subscription expired or invalid, should be removed")
            return False, True
        return False, False
    except Exception as ex:
        logger.error("Unexpected error sending web push: %s", ex)
        return False, False


async def send_web_push_to_user(
    user_id,
    payload: dict,
    settings: Settings,
    db_session,
) -> int:
    """Send web push to all subscriptions for a user. Cleans up expired ones.

    Returns number of successfully sent notifications.
    """
    from sqlalchemy import delete, select
    from app.models.user import WebPushSubscription

    result = await db_session.execute(
        select(WebPushSubscription).where(WebPushSubscription.user_id == user_id)
    )
    subs = result.scalars().all()

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

    if expired_ids:
        await db_session.execute(
            delete(WebPushSubscription).where(WebPushSubscription.id.in_(expired_ids))
        )

    return sent
