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
) -> bool:
    """
    Send a single web push notification.

    Args:
        subscription_info: The PushSubscription JSON (endpoint + keys).
        payload: Dict with at least 'title' and 'body'.
        settings: App settings containing VAPID keys.

    Returns:
        True if sent successfully, False otherwise.
    """
    if not settings.vapid_private_key or not settings.vapid_public_key:
        logger.error("VAPID keys not configured — cannot send web push")
        return False

    try:
        webpush(
            subscription_info=subscription_info,
            data=json.dumps(payload),
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": settings.vapid_claims_email},
        )
        logger.info("Web push sent to %s", subscription_info.get("endpoint", "?")[:60])
        return True
    except WebPushException as ex:
        logger.error("Web push failed: %s", ex)
        # If the subscription is expired/invalid, the caller should remove it
        if ex.response and ex.response.status_code in (404, 410):
            logger.warning("Subscription expired or invalid, should be removed")
        return False
    except Exception as ex:
        logger.error("Unexpected error sending web push: %s", ex)
        return False


def send_web_push_to_all(
    subscriptions: dict[str, dict],
    payload: dict,
    settings: Settings,
) -> int:
    """
    Broadcast a web push to all stored subscriptions.

    Returns:
        Number of successfully sent notifications.
    """
    sent = 0
    for user_id, sub in subscriptions.items():
        if send_web_push(sub, payload, settings):
            sent += 1
        else:
            logger.warning("Failed to send push to user %s", user_id)
    return sent
