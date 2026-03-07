"""API routes for manual scraping triggers."""

import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/scraping", tags=["scraping"])

logger = logging.getLogger(__name__)

VALID_CHAINS = {
    "lidl", "esselunga", "coop", "iperal",
    "carrefour", "conad", "eurospin", "aldi",
    "md-discount", "penny", "pam",
}


class ScrapeResponse(BaseModel):
    status: str
    chain: str
    message: str


class ScrapeResult(BaseModel):
    status: str
    chain: str
    products_found: int
    message: str


async def _resolve_store_id(chain_slug: str):
    """Resolve the target store id for a chain."""
    from app.jobs.scheduler import _resolve_store_id as resolve
    return await resolve(chain_slug)


async def _run_scraper(chain_slug: str, source: str = "auto") -> dict:
    """Run the scraper for a specific chain and return results.

    Args:
        source: "auto" tries direct scraper first, falls back to PromoQui.
                "direct" uses only the chain-specific scraper.
                "promoqui" uses only the PromoQui aggregator.
    """
    scraper = None
    store_id = await _resolve_store_id(chain_slug)

    if source == "tiendeo":
        from app.scrapers.tiendeo import TiendeoScraper
        scraper = TiendeoScraper(chain_slug, store_id=store_id)
    elif source in ("auto", "direct"):
        if chain_slug == "lidl":
            from app.scrapers.lidl import LidlScraper
            scraper = LidlScraper(store_id=store_id)
        elif chain_slug == "esselunga":
            from app.scrapers.esselunga import EsselungaScraper
            scraper = EsselungaScraper()
        elif chain_slug == "coop":
            from app.scrapers.coop import CoopScraper
            scraper = CoopScraper()
        elif chain_slug == "iperal":
            from app.scrapers.iperal import IperalScraper
            scraper = IperalScraper(store_id=store_id)
        elif source == "direct":
            raise ValueError(f"Unknown chain: {chain_slug}")

    if source == "promoqui" or scraper is None:
        from app.scrapers.promoqui import PromoQuiScraper
        scraper = PromoQuiScraper(chain_slug, store_id=store_id)

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

    if source not in ("auto", "direct", "promoqui", "tiendeo"):
        raise HTTPException(status_code=400, detail="source must be 'auto', 'direct', 'promoqui', or 'tiendeo'")

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


@router.post("/catalog-sync/iperal-online", response_model=ScrapeResult)
async def trigger_iperal_online_sync():
    """Trigger Iperal Online catalog sync and wait for it to finish.

    Scrapes the full Iperal Spesa Online product catalog via REST API.
    """
    try:
        from app.scrapers.iperal_online import IperalOnlineScraper

        scraper = IperalOnlineScraper()
        count = await scraper.scrape()
        return ScrapeResult(
            status="completed",
            chain="iperal",
            products_found=count,
            message=f"Iperal Online catalog sync complete: {count} products processed.",
        )
    except Exception as exc:
        logger.exception("Iperal Online catalog sync failed.")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/catalog-sync/esselunga-online", response_model=ScrapeResult)
async def trigger_esselunga_online_sync():
    """Trigger Esselunga Online catalog sync and wait for it to finish.

    Scrapes the Esselunga Spesa Online product catalog via REST API.
    """
    try:
        from app.scrapers.esselunga_online import EsselungaOnlineScraper

        scraper = EsselungaOnlineScraper()
        count = await scraper.scrape()
        return ScrapeResult(
            status="completed",
            chain="esselunga",
            products_found=count,
            message=f"Esselunga Online catalog sync complete: {count} products processed.",
        )
    except Exception as exc:
        logger.exception("Esselunga Online catalog sync failed.")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/catalog-sync/carrefour-online", response_model=ScrapeResult)
async def trigger_carrefour_online_sync():
    """Trigger Carrefour Online catalog sync and wait for it to finish.

    Scrapes the Carrefour Italy product catalog via sitemap + page parsing.
    """
    try:
        from app.scrapers.carrefour_online import CarrefourOnlineScraper

        scraper = CarrefourOnlineScraper()
        count = await scraper.scrape()
        return ScrapeResult(
            status="completed",
            chain="carrefour",
            products_found=count,
            message=f"Carrefour Online catalog sync complete: {count} products processed.",
        )
    except Exception as exc:
        logger.exception("Carrefour Online catalog sync failed.")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/catalog-sync/penny-online", response_model=ScrapeResult)
async def trigger_penny_online_sync():
    """Trigger Penny Market Online catalog sync and wait for it to finish.

    Scrapes the Penny Market Italy product catalog via sitemap + SSR page parsing.
    """
    try:
        from app.scrapers.penny_online import PennyOnlineScraper

        scraper = PennyOnlineScraper()
        count = await scraper.scrape()
        return ScrapeResult(
            status="completed",
            chain="penny",
            products_found=count,
            message=f"Penny Online catalog sync complete: {count} products processed.",
        )
    except Exception as exc:
        logger.exception("Penny Online catalog sync failed.")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/backfill-images")
async def trigger_image_backfill(limit: int = 50):
    """Find images for products without image_url.

    Uses Claude Haiku for query generation, then Open Food Facts + Google Images.
    """
    try:
        from app.config import get_settings
        from app.database import async_session
        from app.services.image_finder import ProductImageFinder

        settings = get_settings()
        async with async_session() as session:
            finder = ProductImageFinder(
                anthropic_api_key=settings.anthropic_api_key or None,
            )
            updated = await finder.backfill(session, limit=limit)
            return {
                "status": "completed",
                "images_found": updated,
                "message": f"Found images for {updated} products (searched {limit}).",
            }
    except Exception as exc:
        logger.exception("Image backfill failed.")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/dedup-products")
async def dedup_products(dry_run: bool = True):
    """Deduplicate products across chains using fuzzy matching.

    Finds cross-source duplicates (e.g. same product from Iperal and Esselunga)
    and merges them: keeps the richer product, moves offers + watchlist entries.

    Query params:
        dry_run: If true (default), only report duplicates without merging.
    """
    from collections import defaultdict
    from sqlalchemy import select, update, delete, func
    from app.database import async_session
    from app.models import Product
    from app.models.offer import Offer
    from app.models.user import UserWatchlist
    from app.services.product_matcher import ProductMatcher

    pm = ProductMatcher()

    def _richness(p) -> int:
        score = 0
        if p.image_url:
            score += 3
        if p.category and p.category != "Supermercato":
            score += 2
        if p.subcategory:
            score += 1
        if p.unit:
            score += 1
        if p.barcode:
            score += 1
        return score

    async with async_session() as session:
        result = await session.execute(select(Product))
        all_products = list(result.scalars().all())

        by_brand: dict = defaultdict(list)
        for p in all_products:
            by_brand[p.brand].append(p)

        merge_pairs: list[tuple] = []
        seen_ids = set()

        for brand, products in by_brand.items():
            if len(products) < 2:
                continue
            products.sort(key=lambda p: _richness(p), reverse=True)

            for i, p1 in enumerate(products):
                if p1.id in seen_ids:
                    continue
                for j in range(i + 1, len(products)):
                    p2 = products[j]
                    if p2.id in seen_ids:
                        continue
                    if p1.source and p2.source and p1.source == p2.source:
                        continue

                    score = pm.fuzzy_match(
                        p1.name, p2.name,
                        brand1=p1.brand, brand2=p2.brand,
                    )

                    cb1 = pm.normalize_brand(p1.brand)
                    cb2 = pm.normalize_brand(p2.brand)
                    threshold = 80 if cb1 and cb2 and cb1 == cb2 else 85

                    if score >= threshold:
                        merge_pairs.append((p1, p2))
                        seen_ids.add(p2.id)

        if dry_run:
            samples = [
                {
                    "keep": {"name": k.name[:60], "source": k.source, "brand": k.brand},
                    "delete": {"name": d.name[:60], "source": d.source, "brand": d.brand},
                }
                for k, d in merge_pairs[:50]
            ]
            return {
                "status": "dry_run",
                "duplicates_found": len(merge_pairs),
                "samples": samples,
                "message": f"Found {len(merge_pairs)} duplicate pairs. Set dry_run=false to merge.",
            }

        # Execute merges
        merged = 0
        for keep, dup in merge_pairs:
            try:
                await session.execute(
                    update(Offer)
                    .where(Offer.product_id == dup.id)
                    .values(product_id=keep.id)
                )

                existing_wl = await session.execute(
                    select(UserWatchlist.user_id)
                    .where(UserWatchlist.product_id == keep.id)
                )
                existing_user_ids = {row[0] for row in existing_wl.fetchall()}

                if existing_user_ids:
                    await session.execute(
                        delete(UserWatchlist)
                        .where(
                            UserWatchlist.product_id == dup.id,
                            UserWatchlist.user_id.in_(existing_user_ids),
                        )
                    )

                await session.execute(
                    update(UserWatchlist)
                    .where(UserWatchlist.product_id == dup.id)
                    .values(product_id=keep.id)
                )

                if not keep.image_url and dup.image_url:
                    keep.image_url = dup.image_url
                if (not keep.category or keep.category == "Supermercato") and dup.category:
                    keep.category = dup.category
                if not keep.subcategory and dup.subcategory:
                    keep.subcategory = dup.subcategory
                if not keep.unit and dup.unit:
                    keep.unit = dup.unit

                await session.execute(
                    delete(Product).where(Product.id == dup.id)
                )
                merged += 1
            except Exception:
                logger.exception("Failed to merge %s -> %s", dup.id, keep.id)
                await session.rollback()
                raise HTTPException(
                    status_code=500,
                    detail=f"Merge failed at pair {merged + 1}. Rolled back.",
                )

        await session.commit()

        return {
            "status": "completed",
            "duplicates_found": len(merge_pairs),
            "merged": merged,
            "message": f"Merged {merged} duplicate products.",
        }


@router.post("/fix-ppu-units")
async def fix_ppu_units():
    """Batch-fix offers where unit_reference='pz' but PPU suggests kg or l.

    Finds offers where price_per_unit > offer_price * 1.5 and unit_reference='pz',
    then re-infers the correct unit using product name keywords.
    """
    from decimal import Decimal
    from sqlalchemy import select
    from app.database import async_session
    from app.models import Product
    from app.models.offer import Offer
    from app.services.unit_price_calculator import UnitPriceCalculator

    fixed = 0
    total_suspect = 0

    async with async_session() as session:
        # Find suspect offers: pz but PPU >> offer_price
        stmt = (
            select(Offer, Product.name, Product.unit)
            .join(Product, Offer.product_id == Product.id)
            .where(
                Offer.unit_reference == "pz",
                Offer.price_per_unit.isnot(None),
                Offer.offer_price.isnot(None),
                Offer.price_per_unit > Offer.offer_price * Decimal("1.5"),
            )
        )
        result = await session.execute(stmt)
        rows = result.all()
        total_suspect = len(rows)

        for offer, product_name, product_unit in rows:
            new_unit = UnitPriceCalculator.infer_unit_reference(
                offer.offer_price,
                offer.price_per_unit,
                product_name,
                "pz",
                product_unit=product_unit,
            )
            if new_unit != "pz":
                offer.unit_reference = new_unit
                fixed += 1

        if fixed:
            await session.commit()

    return {
        "status": "completed",
        "suspect_offers": total_suspect,
        "fixed": fixed,
        "message": f"Fixed {fixed}/{total_suspect} offers with incorrect 'pz' unit.",
    }


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
