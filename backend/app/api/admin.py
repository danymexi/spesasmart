"""Admin API routes: scraping status, product stats, manual trigger."""

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import Chain, Offer, Product
from app.models.user import UserProfile

router = APIRouter(prefix="/admin", tags=["admin"])


# --- Admin guard ---

async def require_admin(user: UserProfile = Depends(get_current_user)) -> UserProfile:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


# --- Schemas ---

class ScrapingChainStatus(BaseModel):
    chain_name: str
    chain_slug: str
    latest_offer_date: datetime | None
    active_offers: int
    total_products: int
    hours_since_update: float | None


class ScrapingStatusResponse(BaseModel):
    chains: list[ScrapingChainStatus]
    total_offers: int
    total_products: int


class ProductStatsResponse(BaseModel):
    total_products: int
    products_with_images: int
    products_without_images: int
    products_by_category: dict[str, int]
    total_active_offers: int
    avg_discount_pct: float | None


class ProductEditRequest(BaseModel):
    name: str | None = None
    brand: str | None = None
    category: str | None = None
    image_url: str | None = None


class ProductResponse(BaseModel):
    id: uuid.UUID
    name: str
    brand: str | None
    category: str | None
    image_url: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TriggerResponse(BaseModel):
    status: str
    chain: str
    message: str


# --- Endpoints ---

@router.get("/scraping/status", response_model=ScrapingStatusResponse)
async def get_scraping_status(
    admin: UserProfile = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get scraping status per chain."""
    today = date.today()
    now = datetime.utcnow()

    # Get all chains
    chains_result = await db.execute(select(Chain).order_by(Chain.name))
    chains = chains_result.scalars().all()

    chain_statuses = []
    for chain in chains:
        # Latest offer created_at
        latest_result = await db.execute(
            select(func.max(Offer.created_at)).where(Offer.chain_id == chain.id)
        )
        latest_date = latest_result.scalar()

        # Active offers count
        active_result = await db.execute(
            select(func.count(Offer.id)).where(
                Offer.chain_id == chain.id,
                Offer.valid_from <= today,
                Offer.valid_to >= today,
            )
        )
        active_count = active_result.scalar() or 0

        # Total products with offers from this chain
        products_result = await db.execute(
            select(func.count(func.distinct(Offer.product_id))).where(
                Offer.chain_id == chain.id,
            )
        )
        total_products = products_result.scalar() or 0

        hours_since = None
        if latest_date:
            delta = now - latest_date.replace(tzinfo=None)
            hours_since = round(delta.total_seconds() / 3600, 1)

        chain_statuses.append(ScrapingChainStatus(
            chain_name=chain.name,
            chain_slug=chain.slug,
            latest_offer_date=latest_date,
            active_offers=active_count,
            total_products=total_products,
            hours_since_update=hours_since,
        ))

    # Totals
    total_offers_result = await db.execute(
        select(func.count(Offer.id)).where(
            Offer.valid_from <= today,
            Offer.valid_to >= today,
        )
    )
    total_products_result = await db.execute(select(func.count(Product.id)))

    return ScrapingStatusResponse(
        chains=chain_statuses,
        total_offers=total_offers_result.scalar() or 0,
        total_products=total_products_result.scalar() or 0,
    )


@router.get("/products/stats", response_model=ProductStatsResponse)
async def get_product_stats(
    admin: UserProfile = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get product database statistics."""
    today = date.today()

    total = (await db.execute(select(func.count(Product.id)))).scalar() or 0
    with_images = (await db.execute(
        select(func.count(Product.id)).where(
            Product.image_url.isnot(None), Product.image_url != ""
        )
    )).scalar() or 0

    # By category
    cat_result = await db.execute(
        select(Product.category, func.count(Product.id))
        .where(Product.category.isnot(None))
        .group_by(Product.category)
        .order_by(func.count(Product.id).desc())
    )
    by_category = dict(cat_result.all())

    # Active offers
    active_offers = (await db.execute(
        select(func.count(Offer.id)).where(
            Offer.valid_from <= today, Offer.valid_to >= today,
        )
    )).scalar() or 0

    # Average discount
    avg_discount = (await db.execute(
        select(func.avg(Offer.discount_pct)).where(
            Offer.discount_pct.isnot(None),
            Offer.valid_from <= today,
            Offer.valid_to >= today,
        )
    )).scalar()

    return ProductStatsResponse(
        total_products=total,
        products_with_images=with_images,
        products_without_images=total - with_images,
        products_by_category=by_category,
        total_active_offers=active_offers,
        avg_discount_pct=round(float(avg_discount), 1) if avg_discount else None,
    )


@router.get("/products/review", response_model=list[ProductResponse])
async def get_products_for_review(
    admin: UserProfile = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
):
    """Get products without images or category (for manual review)."""
    result = await db.execute(
        select(Product)
        .where(
            (Product.image_url.is_(None)) | (Product.category.is_(None))
        )
        .order_by(Product.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


@router.patch("/products/{product_id}", response_model=ProductResponse)
async def edit_product(
    product_id: uuid.UUID,
    data: ProductEditRequest,
    admin: UserProfile = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Edit product metadata (admin only)."""
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if data.name is not None:
        product.name = data.name
    if data.brand is not None:
        product.brand = data.brand
    if data.category is not None:
        product.category = data.category
    if data.image_url is not None:
        product.image_url = data.image_url

    await db.flush()
    await db.refresh(product)
    return product


@router.post("/dedup-barcodes")
async def dedup_barcodes(
    admin: UserProfile = Depends(require_admin),
):
    """Merge duplicate products that share the same valid EAN barcode.

    Keeps the product with the most offers as canonical, reassigns all
    offers and watchlist entries, then deletes the duplicates.
    """
    from app.services.product_matcher import ProductMatcher

    try:
        merged = await ProductMatcher.merge_barcode_duplicates()
        return {
            "status": "completed",
            "merged": merged,
            "message": f"Merged {merged} duplicate products by barcode.",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/scraping/trigger/{chain_slug}", response_model=TriggerResponse)
async def trigger_scraping(
    chain_slug: str,
    admin: UserProfile = Depends(require_admin),
):
    """Manually trigger scraping for a chain (admin only)."""
    valid_chains = ["lidl", "esselunga", "coop", "iperal"]
    if chain_slug not in valid_chains:
        raise HTTPException(status_code=400, detail=f"Invalid chain. Valid: {valid_chains}")

    # Delegate to existing scraping function
    from app.api.scraping import _run_scraper
    try:
        result = await _run_scraper(chain_slug)
        return TriggerResponse(
            status="ok",
            chain=chain_slug,
            message=f"Found {result.get('products_found', 0)} products",
        )
    except Exception as e:
        return TriggerResponse(status="error", chain=chain_slug, message=str(e))
