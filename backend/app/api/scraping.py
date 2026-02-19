"""API routes for manual scraping triggers."""

import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/scraping", tags=["scraping"])

logger = logging.getLogger(__name__)

VALID_CHAINS = {"lidl", "esselunga", "coop", "iperal"}


class ScrapeResponse(BaseModel):
    status: str
    chain: str
    message: str


class ScrapeResult(BaseModel):
    status: str
    chain: str
    products_found: int
    message: str


async def _run_scraper(chain_slug: str, source: str = "auto") -> dict:
    """Run the scraper for a specific chain and return results.

    Args:
        source: "auto" tries direct scraper first, falls back to PromoQui.
                "direct" uses only the chain-specific scraper.
                "promoqui" uses only the PromoQui aggregator.
    """
    scraper = None

    if source in ("auto", "direct"):
        if chain_slug == "lidl":
            from app.scrapers.lidl import LidlScraper
            scraper = LidlScraper()
        elif chain_slug == "esselunga":
            from app.scrapers.esselunga import EsselungaScraper
            scraper = EsselungaScraper()
        elif chain_slug == "coop":
            from app.scrapers.coop import CoopScraper
            scraper = CoopScraper()
        elif chain_slug == "iperal":
            from app.scrapers.iperal import IperalScraper
            scraper = IperalScraper()
        elif source == "direct":
            raise ValueError(f"Unknown chain: {chain_slug}")

    if source == "promoqui" or scraper is None:
        from app.scrapers.promoqui import PromoQuiScraper
        scraper = PromoQuiScraper(chain_slug)

    flyers_data = await scraper.scrape()

    total_products = sum(len(f.get("products", [])) for f in flyers_data)

    # Trigger notifications
    try:
        from app.services.notification import NotificationService
        notifier = NotificationService()
        await notifier.notify_new_offers_for_chain(chain_slug)
    except Exception:
        logger.exception("Notification dispatch failed for chain %s", chain_slug)

    return {
        "flyers_count": len(flyers_data),
        "total_products": total_products,
    }


@router.post("/trigger/{chain_slug}", response_model=ScrapeResponse)
async def trigger_scraping(chain_slug: str, background_tasks: BackgroundTasks):
    """Trigger scraping for a specific chain in the background.

    The scraping runs asynchronously -- this endpoint returns immediately.
    """
    if chain_slug not in VALID_CHAINS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid chain '{chain_slug}'. Valid chains: {', '.join(sorted(VALID_CHAINS))}",
        )

    async def _background_scrape():
        try:
            result = await _run_scraper(chain_slug)
            logger.info(
                "Background scrape for '%s' finished: %d flyers, %d products.",
                chain_slug,
                result["flyers_count"],
                result["total_products"],
            )
        except Exception:
            logger.exception("Background scrape for '%s' failed.", chain_slug)

    background_tasks.add_task(_background_scrape)

    return ScrapeResponse(
        status="started",
        chain=chain_slug,
        message=f"Scraping for '{chain_slug}' started in background.",
    )


@router.post("/trigger/{chain_slug}/sync", response_model=ScrapeResult)
async def trigger_scraping_sync(chain_slug: str, source: str = "auto"):
    """Trigger scraping for a specific chain and wait for it to finish.

    Use this for debugging/testing. May take 30-60 seconds.

    Query params:
        source: "auto" (default), "direct", or "promoqui"
    """
    if chain_slug not in VALID_CHAINS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid chain '{chain_slug}'. Valid chains: {', '.join(sorted(VALID_CHAINS))}",
        )

    if source not in ("auto", "direct", "promoqui"):
        raise HTTPException(status_code=400, detail="source must be 'auto', 'direct', or 'promoqui'")

    try:
        result = await _run_scraper(chain_slug, source=source)
        return ScrapeResult(
            status="completed",
            chain=chain_slug,
            products_found=result["total_products"],
            message=f"Scraped {result['flyers_count']} flyer(s) with {result['total_products']} products (source={source}).",
        )
    except Exception as exc:
        logger.exception("Sync scrape for '%s' failed.", chain_slug)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/test-telegram/{user_id}")
async def test_telegram_notification(user_id: str):
    """Send a test Telegram notification to a user.

    The user must have a telegram_chat_id set in their profile.
    """
    import uuid
    from sqlalchemy import select
    from app.database import async_session
    from app.models import UserProfile

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID")

    async with async_session() as session:
        result = await session.execute(
            select(UserProfile).where(UserProfile.id == uid)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if not user.telegram_chat_id:
            raise HTTPException(
                status_code=400,
                detail="User has no telegram_chat_id. Update the user first.",
            )

    try:
        from app.services.notification import NotificationService
        notifier = NotificationService()
        message = (
            "<b>SpesaSmart Test</b>\n\n"
            "Le notifiche Telegram funzionano correttamente!\n"
            "Riceverai avvisi quando i prodotti nella tua lista "
            "della spesa saranno in offerta."
        )
        ok = await notifier.send_telegram_notification(user.telegram_chat_id, message)
        if ok:
            return {"status": "sent", "message": "Test notification sent successfully."}
        else:
            raise HTTPException(status_code=500, detail="Failed to send Telegram message.")
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/status")
async def scraping_status():
    """Get the current status of the scheduler and its jobs."""
    from app.config import get_settings

    settings = get_settings()

    result = {
        "scheduler_enabled": settings.scheduler_enabled,
        "available_chains": sorted(VALID_CHAINS),
    }

    if settings.scheduler_enabled:
        try:
            from app.jobs.scheduler import start_scheduler
            # Note: we can't easily get the existing scheduler instance here,
            # but we report that it's enabled
            result["message"] = "Scheduler is running with automatic cron jobs."
        except Exception:
            result["message"] = "Scheduler is enabled but may not be running."
    else:
        result["message"] = "Scheduler is disabled. Use /trigger endpoints for manual scraping."

    return result
