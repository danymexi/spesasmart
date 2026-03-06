"""Celery tasks for web scraping pipeline."""

import asyncio
import logging
from datetime import datetime, timezone

from tasks import celery_app

logger = logging.getLogger(__name__)

SCRAPER_MAP = {
    "esselunga": "scrapers.esselunga.EsselungaScraper",
    "iperal": "scrapers.iperal.IperalScraper",
}


def _get_scraper_class(chain_slug: str):
    """Dynamically import and return the scraper class."""
    if chain_slug not in SCRAPER_MAP:
        raise ValueError(f"No scraper configured for chain: {chain_slug}")

    module_path, class_name = SCRAPER_MAP[chain_slug].rsplit(".", 1)
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


@celery_app.task(name="tasks.scraping.scrape_chain", bind=True, max_retries=2)
def scrape_chain(self, chain_slug: str):
    """
    Main scraping task. Spawns the appropriate scraper and processes results.
    """
    logger.info(f"Starting scrape for chain: {chain_slug}")

    try:
        scraper_cls = _get_scraper_class(chain_slug)
        scraper = scraper_cls()

        # Run the async scraper in a sync Celery task
        products = asyncio.run(_run_scraper(scraper))

        logger.info(
            f"Scrape completed for {chain_slug}: "
            f"{len(products)} products scraped"
        )
        return {
            "chain": chain_slug,
            "products_scraped": len(products),
            "errors": scraper.errors,
        }

    except Exception as e:
        logger.error(f"Scrape failed for {chain_slug}: {e}")
        raise self.retry(exc=e, countdown=300)  # Retry in 5 minutes


async def _run_scraper(scraper):
    """Run the async scraper and collect all products."""
    products = []
    async for product in scraper.scrape_all_products():
        products.append(product)
    return products
