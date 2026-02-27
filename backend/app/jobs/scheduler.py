"""APScheduler job configuration for automated scraping."""

import asyncio
import logging
import uuid

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

# Target store names by chain slug.
# These are the specific stores the user wants to track.
TARGET_STORES: dict[str, str] = {
    "esselunga": "Esselunga Macherio",
    "iperal": "Iperal Lesmo",
    "lidl": "Lidl Biassono",
    "coop": "Coop Monza",
}


async def _resolve_store_id(chain_slug: str) -> uuid.UUID | None:
    """Look up the target store for a chain and return its id."""
    store_name = TARGET_STORES.get(chain_slug)
    if not store_name:
        return None

    from sqlalchemy import select
    from app.database import async_session
    from app.models.store import Store

    async with async_session() as session:
        stmt = select(Store).where(Store.name == store_name)
        result = await session.execute(stmt)
        store = result.scalar_one_or_none()
        if store:
            logger.info("Resolved target store: %s -> %s", chain_slug, store.id)
            return store.id
        else:
            logger.warning(
                "Target store '%s' not found in DB for chain '%s'.",
                store_name,
                chain_slug,
            )
            return None


async def scrape_chain(chain_slug: str):
    """Run scraper for a specific chain using multi-source strategy.

    Strategy (Tiendeo-first):
        1. Tiendeo (primary) — structured data, HTTP-only, all 4 chains.
        2. Direct scraper (supplementary) — chain-specific, for extra products.
        3. PromoQui (fallback) — only if Tiendeo returned 0 products.
    """
    logger.info("Starting scrape job for chain: %s", chain_slug)

    store_id = await _resolve_store_id(chain_slug)
    total_products = 0

    # --- 1. Tiendeo (primary) ---
    try:
        from app.scrapers.tiendeo import TiendeoScraper

        tiendeo = TiendeoScraper(chain_slug, store_id=store_id)
        tiendeo_results = await tiendeo.scrape()
        tiendeo_count = sum(len(f.get("products", [])) for f in tiendeo_results)
        total_products += tiendeo_count
        logger.info(
            "Tiendeo returned %d products for '%s'.", tiendeo_count, chain_slug
        )
    except Exception:
        logger.exception("Tiendeo scraping failed for '%s'.", chain_slug)
        tiendeo_count = 0

    # --- 2. Direct scraper (supplementary for Lidl) ---
    try:
        if chain_slug == "lidl":
            from app.scrapers.lidl import LidlScraper

            scraper = LidlScraper(store_id=store_id)
            direct_results = await scraper.scrape()
            direct_count = sum(len(f.get("products", [])) for f in direct_results)
            total_products += direct_count
            logger.info(
                "Direct scraper returned %d products for '%s'.",
                direct_count,
                chain_slug,
            )
    except Exception:
        logger.exception("Direct scraper failed for '%s'.", chain_slug)

    # --- 3. PromoQui (fallback if Tiendeo returned nothing) ---
    if tiendeo_count == 0:
        try:
            from app.scrapers.promoqui import PromoQuiScraper

            pq = PromoQuiScraper(chain_slug, store_id=store_id)
            pq_results = await pq.scrape()
            pq_count = sum(len(f.get("products", [])) for f in pq_results)
            total_products += pq_count
            logger.info(
                "PromoQui fallback returned %d products for '%s'.",
                pq_count,
                chain_slug,
            )
        except Exception:
            logger.exception("PromoQui fallback failed for '%s'.", chain_slug)

    logger.info(
        "Scrape completed for '%s': %d total products.", chain_slug, total_products
    )

    # Trigger notifications after scraping
    try:
        from app.services.notification import NotificationService

        notifier = NotificationService()
        await notifier.notify_new_offers_for_chain(chain_slug)
    except Exception:
        logger.exception("Notification dispatch failed for '%s'.", chain_slug)


async def scrape_all_chains():
    """Scrape all chains sequentially."""
    for slug in ["esselunga", "lidl", "coop", "iperal"]:
        await scrape_chain(slug)


def start_scheduler() -> AsyncIOScheduler:
    """Configure and start the APScheduler."""
    scheduler = AsyncIOScheduler()

    # Lidl: every Monday at 6:00 (weekly flyer Mon-Sun)
    scheduler.add_job(
        scrape_chain,
        CronTrigger(day_of_week="mon", hour=6, minute=0),
        args=["lidl"],
        id="scrape_lidl",
        name="Scrape Lidl weekly offers",
        replace_existing=True,
    )

    # Esselunga: Monday and Thursday at 6:30
    scheduler.add_job(
        scrape_chain,
        CronTrigger(day_of_week="mon,thu", hour=6, minute=30),
        args=["esselunga"],
        id="scrape_esselunga",
        name="Scrape Esselunga flyers",
        replace_existing=True,
    )

    # Coop: every Monday at 7:00
    scheduler.add_job(
        scrape_chain,
        CronTrigger(day_of_week="mon", hour=7, minute=0),
        args=["coop"],
        id="scrape_coop",
        name="Scrape Coop flyers",
        replace_existing=True,
    )

    # Iperal: Monday and Thursday at 7:30
    scheduler.add_job(
        scrape_chain,
        CronTrigger(day_of_week="mon,thu", hour=7, minute=30),
        args=["iperal"],
        id="scrape_iperal",
        name="Scrape Iperal flyers",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started with %d jobs", len(scheduler.get_jobs()))
    return scheduler
