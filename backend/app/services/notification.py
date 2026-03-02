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

from app.config import Settings, get_settings
from app.database import async_session
from app.models import Chain, Offer, Product, UserBrand, UserProfile, UserWatchlist

logger = logging.getLogger(__name__)

# Expo push API endpoint
_EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


class NotificationService:
    """Sends watchlist-based notifications over Telegram and Expo Push."""

    def __init__(self) -> None:
        self._settings: Settings = get_settings()
        self._telegram_token: str = self._settings.telegram_bot_token
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
    # Web Push
    # ------------------------------------------------------------------

    async def send_web_push_notification(
        self,
        user_id,
        title: str,
        body: str,
        *,
        session: AsyncSession,
    ) -> bool:
        """Send a Web Push notification to all subscriptions for a user."""
        from app.services.web_push_sender import send_web_push_to_user

        payload = {"title": title, "body": body}
        sent = await send_web_push_to_user(
            user_id, payload, self._settings, session
        )
        if sent > 0:
            logger.info("Web push sent to user %s (%d subs)", user_id, sent)
            return True
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
    # Brand matching
    # ------------------------------------------------------------------

    async def check_brand_alerts(
        self,
        offers: list[Offer],
        *,
        session: AsyncSession | None = None,
    ) -> list[tuple[UserProfile, UserBrand, Offer]]:
        """Match a batch of offers against users' favourite brands.

        Returns ``(user, user_brand, offer)`` triples for every match.
        """
        close_session = False
        if session is None:
            session = async_session()
            close_session = True

        try:
            if not offers:
                return []

            # Ensure products are loaded
            product_ids = {o.product_id for o in offers}
            prod_stmt = select(Product).where(Product.id.in_(product_ids))
            prod_result = await session.execute(prod_stmt)
            products_map: dict = {
                p.id: p for p in prod_result.scalars().all()
            }

            # Get all user brands with notify=True
            stmt = (
                select(UserBrand)
                .options(joinedload(UserBrand.user))
                .where(UserBrand.notify.is_(True))
            )
            result = await session.execute(stmt)
            user_brands: list[UserBrand] = list(result.scalars().unique().all())

            if not user_brands:
                return []

            alerts: list[tuple[UserProfile, UserBrand, Offer]] = []

            for offer in offers:
                product = products_map.get(offer.product_id)
                if not product or not product.brand:
                    continue

                product_brand_lower = product.brand.lower()
                product_category_lower = (product.category or "").lower()

                for ub in user_brands:
                    if ub.brand_name.lower() not in product_brand_lower:
                        continue
                    if ub.category and ub.category.lower() != product_category_lower:
                        continue
                    alerts.append((ub.user, ub, offer))

            logger.info(
                "Brand check: %d offers -> %d alerts",
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
            watchlist_alerts = await self.check_watchlist_alerts(offers, session=session)

            # Check brand matches
            brand_alerts = await self.check_brand_alerts(offers, session=session)

            # Merge and deduplicate by (user_id, offer_id)
            seen: set[tuple] = set()
            all_alerts: list[tuple] = []
            for user, _entry, offer in watchlist_alerts + brand_alerts:
                key = (user.id, offer.id)
                if key not in seen:
                    seen.add(key)
                    all_alerts.append((user, _entry, offer))

            if not all_alerts:
                logger.info(
                    "No matches for chain '%s' (%d offers).",
                    chain_slug,
                    len(offers),
                )
                return 0

            # Dispatch notifications (skip users in digest mode)
            sent_count = 0
            for user, _entry, offer in all_alerts:
                if getattr(user, "notification_mode", "instant") == "digest":
                    continue

                product: Product = offer.product
                chain_obj: Chain = offer.chain
                message = self.format_offer_message(offer, product, chain_obj)
                title = f"Offerta: {product.name}"
                plain_body = (
                    message.replace("<b>", "")
                    .replace("</b>", "")
                    .replace("<s>", "")
                    .replace("</s>", "")
                )

                if user.telegram_chat_id:
                    ok = await self.send_telegram_notification(user.telegram_chat_id, message)
                    if ok:
                        sent_count += 1

                if user.push_token:
                    ok = await self.send_push_notification(user.push_token, title, plain_body)
                    if ok:
                        sent_count += 1

                # Web Push
                ok = await self.send_web_push_notification(
                    user.id, title, plain_body, session=session
                )
                if ok:
                    sent_count += 1

            logger.info(
                "Chain '%s': dispatched %d notifications for %d alerts.",
                chain_slug,
                sent_count,
                len(all_alerts),
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

            # 2. Find matching watchlist + brand entries
            watchlist_alerts = await self.check_watchlist_alerts(
                offers, session=session
            )
            brand_alerts = await self.check_brand_alerts(
                offers, session=session
            )

            # Merge and deduplicate by (user_id, offer_id)
            seen: set[tuple] = set()
            all_alerts: list[tuple] = []
            for user, _entry, offer in watchlist_alerts + brand_alerts:
                key = (user.id, offer.id)
                if key not in seen:
                    seen.add(key)
                    all_alerts.append((user, _entry, offer))

            if not all_alerts:
                logger.info(
                    "No matches for flyer %s (%d offers).",
                    flyer_id,
                    len(offers),
                )
                return 0

            # 3. Dispatch notifications (skip users in digest mode)
            sent_count = 0

            for user, _watchlist_entry, offer in all_alerts:
                if getattr(user, "notification_mode", "instant") == "digest":
                    continue

                product: Product = offer.product
                chain: Chain = offer.chain
                message = self.format_offer_message(offer, product, chain)
                title = f"Offerta: {product.name}"
                plain_body = (
                    message.replace("<b>", "")
                    .replace("</b>", "")
                    .replace("<s>", "")
                    .replace("</s>", "")
                )

                # Telegram
                if user.telegram_chat_id:
                    ok = await self.send_telegram_notification(
                        user.telegram_chat_id, message
                    )
                    if ok:
                        sent_count += 1

                # Expo push
                if user.push_token:
                    ok = await self.send_push_notification(
                        user.push_token, title, plain_body
                    )
                    if ok:
                        sent_count += 1

                # Web Push
                ok = await self.send_web_push_notification(
                    user.id, title, plain_body, session=session
                )
                if ok:
                    sent_count += 1

            logger.info(
                "Flyer %s: dispatched %d notifications for %d alerts.",
                flyer_id,
                sent_count,
                len(all_alerts),
            )
            return sent_count
        finally:
            if close_session:
                await session.close()

    # ------------------------------------------------------------------
    # Weekly digest
    # ------------------------------------------------------------------

    async def send_weekly_digest(self) -> int:
        """Collect all active offers for digest-mode users' watchlists/brands
        and send a single grouped notification per user.

        Returns the number of users notified.
        """
        async with async_session() as session:
            # Get all users with digest mode
            stmt = select(UserProfile).where(
                UserProfile.notification_mode == "digest"
            )
            result = await session.execute(stmt)
            digest_users: list[UserProfile] = list(result.scalars().all())

            if not digest_users:
                logger.info("No digest-mode users found.")
                return 0

            from datetime import date as date_type

            today = date_type.today()

            # Get all currently valid offers with product and chain info
            offers_stmt = (
                select(Offer)
                .options(
                    joinedload(Offer.product),
                    joinedload(Offer.chain),
                )
                .where(
                    Offer.valid_from <= today,
                    Offer.valid_to >= today,
                )
            )
            offers_result = await session.execute(offers_stmt)
            all_offers: list[Offer] = list(offers_result.scalars().unique().all())

            if not all_offers:
                logger.info("No active offers for digest.")
                return 0

            notified = 0
            for user in digest_users:
                # Collect watchlist matches
                wl_stmt = select(UserWatchlist).where(
                    UserWatchlist.user_id == user.id
                )
                wl_result = await session.execute(wl_stmt)
                wl_entries = wl_result.scalars().all()
                wl_product_ids = {e.product_id for e in wl_entries}

                # Collect brand matches
                brand_stmt = select(UserBrand).where(
                    UserBrand.user_id == user.id,
                    UserBrand.notify.is_(True),
                )
                brand_result = await session.execute(brand_stmt)
                user_brands = brand_result.scalars().all()

                # Build product->brand index
                brand_names = {ub.brand_name.lower() for ub in user_brands}

                matching_offers: list[Offer] = []
                seen_ids: set = set()

                for offer in all_offers:
                    if offer.id in seen_ids:
                        continue
                    product = offer.product
                    if not product:
                        continue

                    matched = False
                    # Watchlist match
                    if offer.product_id in wl_product_ids:
                        matched = True
                    # Brand match
                    if not matched and product.brand:
                        for bn in brand_names:
                            if bn in product.brand.lower():
                                matched = True
                                break

                    if matched:
                        seen_ids.add(offer.id)
                        matching_offers.append(offer)

                if not matching_offers:
                    continue

                # Group by chain
                by_chain: dict[str, list[Offer]] = {}
                for o in matching_offers:
                    chain_name = o.chain.name if o.chain else "Altro"
                    by_chain.setdefault(chain_name, []).append(o)

                # Format the digest message
                total = len(matching_offers)
                lines = [f"<b>Questa settimana {total} offerte per te:</b>\n"]
                for chain_name, chain_offers in sorted(by_chain.items()):
                    lines.append(f"\n<b>{chain_name.upper()}</b>")
                    for o in chain_offers[:10]:  # Limit per chain
                        product = o.product
                        price_str = f"{o.offer_price:.2f}\u20ac"
                        discount_str = f" (-{o.discount_pct:.0f}%)" if o.discount_pct else ""
                        lines.append(f"- {product.name}: {price_str}{discount_str}")
                    if len(chain_offers) > 10:
                        lines.append(f"  ...e altre {len(chain_offers) - 10}")

                message = "\n".join(lines)
                title = f"Riepilogo settimanale: {total} offerte"
                plain_body = (
                    message.replace("<b>", "")
                    .replace("</b>", "")
                )

                sent = False
                if user.telegram_chat_id:
                    ok = await self.send_telegram_notification(
                        user.telegram_chat_id, message
                    )
                    if ok:
                        sent = True

                if user.push_token:
                    ok = await self.send_push_notification(
                        user.push_token, title, plain_body
                    )
                    if ok:
                        sent = True

                ok = await self.send_web_push_notification(
                    user.id, title, plain_body, session=session
                )
                if ok:
                    sent = True

                if sent:
                    notified += 1

            logger.info("Weekly digest: notified %d users.", notified)
            return notified
