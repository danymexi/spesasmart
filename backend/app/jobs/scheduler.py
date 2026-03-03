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


async def sync_catalog():
    """Run catalog sync for all chains to populate the full product catalog."""
    logger.info("Starting weekly catalog sync for all chains.")

    from app.scrapers.catalog_scraper import CatalogScraper

    total = 0

    # --- Iperal Online (REST API — fast, structured, thousands of products) ---
    try:
        from app.scrapers.iperal_online import IperalOnlineScraper

        iperal_online = IperalOnlineScraper()
        count = await iperal_online.scrape()
        total += count
        logger.info("Iperal Online catalog: %d products.", count)
    except Exception:
        logger.exception("Iperal Online catalog sync failed.")

    # --- Esselunga Online (REST API — session-based, thousands of products) ---
    try:
        from app.scrapers.esselunga_online import EsselungaOnlineScraper

        esselunga_online = EsselungaOnlineScraper()
        count = await esselunga_online.scrape()
        total += count
        logger.info("Esselunga Online catalog: %d products.", count)
    except Exception:
        logger.exception("Esselunga Online catalog sync failed.")

    # --- Tiendeo catalogs (all chains) ---
    for slug in ["esselunga", "lidl", "coop", "iperal"]:
        try:
            store_id = await _resolve_store_id(slug)
            scraper = CatalogScraper(slug, store_id=store_id)
            count = await scraper.scrape()
            total += count
            logger.info("Catalog sync for '%s': %d products.", slug, count)
        except Exception:
            logger.exception("Catalog sync failed for '%s'.", slug)

    logger.info("Weekly catalog sync complete: %d total products processed.", total)

    # Post-sync image backfill for newly added products
    try:
        from app.database import async_session as get_session
        from app.services.image_finder import ProductImageFinder

        async with get_session() as session:
            finder = ProductImageFinder()
            img_count = await finder.backfill(session, limit=50)
            logger.info("Post-sync image backfill: %d images found.", img_count)
    except Exception:
        logger.exception("Post-sync image backfill failed.")


async def send_weekly_digest():
    """Send the weekly notification digest to users in digest mode."""
    logger.info("Starting weekly notification digest.")
    try:
        from app.services.notification import NotificationService

        notifier = NotificationService()
        notified = await notifier.send_weekly_digest()
        logger.info("Weekly digest complete: %d users notified.", notified)
    except Exception:
        logger.exception("Weekly digest failed.")


async def backfill_unit_prices():
    """Compute price_per_unit for offers that have quantity but no PPU."""
    logger.info("Starting unit price backfill job.")
    from sqlalchemy import select, and_
    from app.database import async_session
    from app.models import Offer, Product
    from app.services.unit_price_calculator import UnitPriceCalculator

    updated = 0
    async with async_session() as session:
        stmt = (
            select(Offer)
            .join(Product, Offer.product_id == Product.id)
            .where(
                Offer.price_per_unit.is_(None),
                Offer.quantity.isnot(None),
                Offer.quantity != "",
            )
            .limit(5000)
        )
        result = await session.execute(stmt)
        offers = result.scalars().all()

        for offer in offers:
            # Eager-load product name for fallback parsing
            prod_result = await session.execute(
                select(Product).where(Product.id == offer.product_id)
            )
            product = prod_result.scalar_one_or_none()

            ppu, unit_ref = UnitPriceCalculator.compute(
                offer.offer_price,
                offer.quantity,
                product_name=product.name if product else None,
                product_unit=product.unit if product else None,
            )
            if ppu is not None:
                offer.price_per_unit = ppu
                offer.unit_reference = unit_ref
                offer.ppu_computed = True
                updated += 1

        await session.commit()
    logger.info("Unit price backfill complete: %d offers updated.", updated)


async def check_stockup_alerts():
    """Check watchlist products for 6-month price lows and send alerts."""
    logger.info("Starting stockup alert check.")
    try:
        from app.services.notification import NotificationService

        notifier = NotificationService()
        sent = await notifier.check_stockup_alerts()
        logger.info("Stockup alert check complete: %d alerts sent.", sent)
    except Exception:
        logger.exception("Stockup alert check failed.")


async def backfill_product_images():
    """Find images for products without image_url."""
    logger.info("Starting product image backfill job.")
    from app.database import async_session
    from app.services.image_finder import ProductImageFinder

    async with async_session() as session:
        finder = ProductImageFinder()
        updated = await finder.backfill(session, limit=500)
        logger.info("Product image backfill complete: %d images found.", updated)


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

    # Weekly notification digest: Monday 8:00 AM
    scheduler.add_job(
        send_weekly_digest,
        CronTrigger(day_of_week="mon", hour=8, minute=0),
        id="weekly_digest",
        name="Weekly notification digest",
        replace_existing=True,
    )

    # Catalog sync: every Sunday at 3:00 AM
    scheduler.add_job(
        sync_catalog,
        CronTrigger(day_of_week="sun", hour=3, minute=0),
        id="sync_catalog",
        name="Weekly catalog sync (all chains)",
        replace_existing=True,
    )

    # Backfill unit prices: every Sunday at 4:00 AM (after catalog sync)
    scheduler.add_job(
        backfill_unit_prices,
        CronTrigger(day_of_week="sun", hour=4, minute=0),
        id="backfill_unit_prices",
        name="Backfill unit prices for offers without PPU",
        replace_existing=True,
    )

    # Stockup alerts: Monday and Thursday at 9:00 AM (after scraping)
    scheduler.add_job(
        check_stockup_alerts,
        CronTrigger(day_of_week="mon,thu", hour=9, minute=0),
        id="check_stockup_alerts",
        name="Check watchlist for stockup opportunities",
        replace_existing=True,
    )

    # Product image backfill: daily at 4:30 AM
    scheduler.add_job(
        backfill_product_images,
        CronTrigger(hour=4, minute=30),
        id="backfill_product_images",
        name="Find images for products without image_url",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started with %d jobs", len(scheduler.get_jobs()))
    return scheduler
