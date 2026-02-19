"""Notification service.

Sends price-alert notifications to users via Telegram and Expo push when
offers matching their watchlist are detected.
"""

import logging
from datetime import date
from decimal import Decimal
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from telegram import Bot
from telegram.error import TelegramError

from app.config import get_settings
from app.database import async_session
from app.models import Chain, Offer, Product, UserProfile, UserWatchlist

logger = logging.getLogger(__name__)

# Expo push API endpoint
_EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


class NotificationService:
    """Sends watchlist-based notifications over Telegram and Expo Push."""

    def __init__(self) -> None:
        settings = get_settings()
        self._telegram_token: str = settings.telegram_bot_token
        self._bot: Bot | None = None

    # ------------------------------------------------------------------
    # Telegram
    # ------------------------------------------------------------------

    def _get_bot(self) -> Bot:
        """Lazily initialise the Telegram Bot instance."""
        if self._bot is None:
            if not self._telegram_token:
                raise RuntimeError(
                    "TELEGRAM_BOT_TOKEN is not configured – "
                    "cannot send Telegram notifications."
                )
            self._bot = Bot(token=self._telegram_token)
        return self._bot

    async def send_telegram_notification(
        self, chat_id: int, message: str
    ) -> bool:
        """Send a single Telegram message.  Returns ``True`` on success."""
        try:
            bot = self._get_bot()
            await bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode="HTML",
            )
            logger.info("Telegram message sent to chat_id=%s", chat_id)
            return True
        except TelegramError as exc:
            logger.error(
                "Telegram send failed for chat_id=%s: %s", chat_id, exc
            )
            return False
        except Exception as exc:
            logger.exception(
                "Unexpected error sending Telegram to chat_id=%s: %s",
                chat_id,
                exc,
            )
            return False

    # ------------------------------------------------------------------
    # Expo Push
    # ------------------------------------------------------------------

    async def send_push_notification(
        self, push_token: str, title: str, body: str
    ) -> bool:
        """Send an Expo push notification.  Returns ``True`` on success."""
        payload = {
            "to": push_token,
            "sound": "default",
            "title": title,
            "body": body,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(_EXPO_PUSH_URL, json=payload)
                response.raise_for_status()

            data = response.json()
            # Expo returns {"data": {"status": "ok"|"error", ...}}
            status = data.get("data", {}).get("status")
            if status == "ok":
                logger.info("Push sent to token=%s…", push_token[:20])
                return True
            else:
                logger.warning(
                    "Expo push returned status=%s for token=%s…: %s",
                    status,
                    push_token[:20],
                    data,
                )
                return False
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Expo push HTTP error for token=%s…: %s",
                push_token[:20],
                exc,
            )
            return False
        except Exception as exc:
            logger.exception(
                "Unexpected error sending push to token=%s…: %s",
                push_token[:20],
                exc,
            )
            return False

    # ------------------------------------------------------------------
    # Watchlist matching
    # ------------------------------------------------------------------

    async def check_watchlist_alerts(
        self,
        offers: list[Offer],
        *,
        session: AsyncSession | None = None,
    ) -> list[tuple[UserProfile, UserWatchlist, Offer]]:
        """Match a batch of offers against users' watchlists.

        Returns a list of ``(user, watchlist_entry, offer)`` triples for
        every match that should trigger a notification.

        A match fires when:
        - ``notify_any_offer`` is True, **or**
        - the offer price is at or below ``target_price``.
        """
        close_session = False
        if session is None:
            session = async_session()
            close_session = True

        try:
            product_ids = {o.product_id for o in offers}
            if not product_ids:
                return []

            stmt = (
                select(UserWatchlist)
                .options(joinedload(UserWatchlist.user))
                .where(UserWatchlist.product_id.in_(product_ids))
            )
            result = await session.execute(stmt)
            entries: list[UserWatchlist] = list(result.scalars().unique().all())

            # Build a fast lookup: product_id -> list of offers
            offers_by_product: dict = {}
            for offer in offers:
                offers_by_product.setdefault(offer.product_id, []).append(offer)

            alerts: list[tuple[UserProfile, UserWatchlist, Offer]] = []

            for entry in entries:
                matching_offers = offers_by_product.get(entry.product_id, [])
                for offer in matching_offers:
                    should_notify = entry.notify_any_offer
                    if (
                        not should_notify
                        and entry.target_price is not None
                        and offer.offer_price <= entry.target_price
                    ):
                        should_notify = True

                    if should_notify:
                        alerts.append((entry.user, entry, offer))

            logger.info(
                "Watchlist check: %d offers -> %d alerts",
                len(offers),
                len(alerts),
            )
            return alerts
        finally:
            if close_session:
                await session.close()

    # ------------------------------------------------------------------
    # Message formatting
    # ------------------------------------------------------------------

    @staticmethod
    def format_offer_message(
        offer: Offer,
        product: Product,
        chain: Chain,
    ) -> str:
        """Build a user-facing Italian HTML message for a single offer."""
        lines: list[str] = []

        lines.append(f"<b>Offerta trovata!</b>")
        lines.append(f"<b>{product.name}</b>")

        if product.brand:
            lines.append(f"Marca: {product.brand}")

        lines.append(f"Catena: {chain.name}")

        # Price line
        if offer.original_price and offer.original_price > offer.offer_price:
            lines.append(
                f"Prezzo: <s>{offer.original_price:.2f}\u20ac</s> "
                f"<b>{offer.offer_price:.2f}\u20ac</b>"
            )
        else:
            lines.append(f"Prezzo: <b>{offer.offer_price:.2f}\u20ac</b>")

        if offer.discount_pct:
            lines.append(f"Sconto: -{offer.discount_pct:.0f}%")

        if offer.quantity:
            lines.append(f"Quantita: {offer.quantity}")

        # Validity
        if offer.valid_from and offer.valid_to:
            lines.append(
                f"Valido: {offer.valid_from.strftime('%d/%m')} – "
                f"{offer.valid_to.strftime('%d/%m/%Y')}"
            )
        elif offer.valid_to:
            lines.append(f"Valido fino al: {offer.valid_to.strftime('%d/%m/%Y')}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # High-level: notify about new offers for a chain
    # ------------------------------------------------------------------

    async def notify_new_offers_for_chain(
        self,
        chain_slug: str,
    ) -> int:
        """Send notifications for watchlist matches across all recent offers
        from the given chain.

        Finds all offers for the chain that are currently valid and triggers
        watchlist alert checks.  Returns the total number of notifications
        sent successfully.
        """
        async with async_session() as session:
            # Find chain
            stmt = select(Chain).where(Chain.slug == chain_slug)
            result = await session.execute(stmt)
            chain = result.scalar_one_or_none()
            if chain is None:
                logger.warning("Chain '%s' not found – skipping notifications.", chain_slug)
                return 0

            # Find all currently valid offers for this chain
            from datetime import date as date_type

            today = date_type.today()
            stmt = (
                select(Offer)
                .options(
                    joinedload(Offer.product),
                    joinedload(Offer.chain),
                )
                .where(
                    Offer.chain_id == chain.id,
                    Offer.valid_from <= today,
                    Offer.valid_to >= today,
                )
            )
            result = await session.execute(stmt)
            offers: list[Offer] = list(result.scalars().unique().all())

            if not offers:
                logger.info("No active offers for chain '%s' – skipping.", chain_slug)
                return 0

            # Check watchlist matches
            alerts = await self.check_watchlist_alerts(offers, session=session)
            if not alerts:
                logger.info(
                    "No watchlist matches for chain '%s' (%d offers).",
                    chain_slug,
                    len(offers),
                )
                return 0

            # Dispatch notifications
            sent_count = 0
            for user, _entry, offer in alerts:
                product: Product = offer.product
                chain_obj: Chain = offer.chain
                message = self.format_offer_message(offer, product, chain_obj)
                title = f"Offerta: {product.name}"

                if user.telegram_chat_id:
                    ok = await self.send_telegram_notification(user.telegram_chat_id, message)
                    if ok:
                        sent_count += 1

                if user.push_token:
                    plain_body = (
                        message.replace("<b>", "")
                        .replace("</b>", "")
                        .replace("<s>", "")
                        .replace("</s>", "")
                    )
                    ok = await self.send_push_notification(user.push_token, title, plain_body)
                    if ok:
                        sent_count += 1

            logger.info(
                "Chain '%s': dispatched %d notifications for %d alerts.",
                chain_slug,
                sent_count,
                len(alerts),
            )
            return sent_count

    # ------------------------------------------------------------------
    # High-level: notify about new offers from a flyer
    # ------------------------------------------------------------------

    async def notify_new_offers(
        self,
        flyer_id,
        *,
        session: AsyncSession | None = None,
    ) -> int:
        """Send notifications for every watchlist match in *flyer_id*.

        Returns the total number of notifications sent successfully.
        """
        close_session = False
        if session is None:
            session = async_session()
            close_session = True

        try:
            # 1. Fetch all offers for this flyer, eagerly loading relations
            stmt = (
                select(Offer)
                .options(
                    joinedload(Offer.product),
                    joinedload(Offer.chain),
                )
                .where(Offer.flyer_id == flyer_id)
            )
            result = await session.execute(stmt)
            offers: list[Offer] = list(result.scalars().unique().all())

            if not offers:
                logger.info("Flyer %s has no offers – skipping.", flyer_id)
                return 0

            # 2. Find matching watchlist entries
            alerts = await self.check_watchlist_alerts(
                offers, session=session
            )
            if not alerts:
                logger.info(
                    "No watchlist matches for flyer %s (%d offers).",
                    flyer_id,
                    len(offers),
                )
                return 0

            # 3. Dispatch notifications
            sent_count = 0

            for user, _watchlist_entry, offer in alerts:
                product: Product = offer.product
                chain: Chain = offer.chain
                message = self.format_offer_message(offer, product, chain)
                title = f"Offerta: {product.name}"

                # Telegram
                if user.telegram_chat_id:
                    ok = await self.send_telegram_notification(
                        user.telegram_chat_id, message
                    )
                    if ok:
                        sent_count += 1

                # Expo push
                if user.push_token:
                    # Strip HTML tags for the push body
                    plain_body = (
                        message.replace("<b>", "")
                        .replace("</b>", "")
                        .replace("<s>", "")
                        .replace("</s>", "")
                    )
                    ok = await self.send_push_notification(
                        user.push_token, title, plain_body
                    )
                    if ok:
                        sent_count += 1

            logger.info(
                "Flyer %s: dispatched %d notifications for %d alerts.",
                flyer_id,
                sent_count,
                len(alerts),
            )
            return sent_count
        finally:
            if close_session:
                await session.close()
