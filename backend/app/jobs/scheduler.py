"""APScheduler job configuration for automated scraping."""

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


async def scrape_chain(chain_slug: str):
    """Run scraper for a specific chain."""
    logger.info("Starting scrape job for chain: %s", chain_slug)
    try:
        if chain_slug == "esselunga":
            from app.scrapers.esselunga import EsselungaScraper

            scraper = EsselungaScraper()
        elif chain_slug == "lidl":
            from app.scrapers.lidl import LidlScraper

            scraper = LidlScraper()
        elif chain_slug == "coop":
            from app.scrapers.coop import CoopScraper

            scraper = CoopScraper()
        elif chain_slug == "iperal":
            from app.scrapers.iperal import IperalScraper

            scraper = IperalScraper()
        else:
            logger.error("Unknown chain: %s", chain_slug)
            return

        await scraper.scrape()
        logger.info("Scrape completed for chain: %s", chain_slug)

        # Trigger notifications after scraping
        from app.services.notification import NotificationService

        notifier = NotificationService()
        await notifier.notify_new_offers_for_chain(chain_slug)

    except Exception:
        logger.exception("Error scraping chain %s", chain_slug)


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
