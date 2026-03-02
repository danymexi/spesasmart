"""API routes for user profiles, watchlist, and stores (JWT-protected)."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.auth import get_current_user
from app.database import get_db
from app.models import Chain, Offer, Product, UserBrand, UserProfile, UserStore, UserWatchlist

router = APIRouter(prefix="/users", tags=["users"])


# --- Schemas ---

class UserResponse(BaseModel):
    id: uuid.UUID
    email: str | None
    telegram_chat_id: int | None
    push_token: str | None
    preferred_zone: str
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdateRequest(BaseModel):
    telegram_chat_id: int | None = None
    push_token: str | None = None
    preferred_zone: str | None = None


class WatchlistAddRequest(BaseModel):
    product_id: uuid.UUID
    target_price: Decimal | None = None
    notify_any_offer: bool = True


class WatchlistItemResponse(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    brand: str | None
    target_price: Decimal | None
    notify_any_offer: bool
    best_current_price: Decimal | None = None
    best_chain: str | None = None

    model_config = {"from_attributes": True}


class StoreAddRequest(BaseModel):
    store_id: uuid.UUID


class UserDealResponse(BaseModel):
    product_id: str
    product_name: str
    brand: str | None
    chain_name: str
    offer_price: Decimal
    original_price: Decimal | None
    discount_pct: Decimal | None
    valid_to: date | None
    image_url: str | None


class BrandAddRequest(BaseModel):
    brand_name: str
    category: str | None = None
    notify: bool = True


class UserBrandResponse(BaseModel):
    id: uuid.UUID
    brand_name: str
    category: str | None
    notify: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AlternativeResponse(BaseModel):
    product_id: str
    product_name: str
    brand: str | None
    category: str | None
    chain_name: str
    offer_price: Decimal
    original_price: Decimal | None
    discount_pct: Decimal | None
    price_per_unit: Decimal | None
    unit_reference: str | None
    valid_to: date | None
    image_url: str | None


class BrandDealResponse(BaseModel):
    product_id: str
    product_name: str
    brand: str | None
    category: str | None
    chain_name: str
    offer_price: Decimal
    original_price: Decimal | None
    discount_pct: Decimal | None
    price_per_unit: Decimal | None
    unit_reference: str | None
    valid_to: date | None
    image_url: str | None


# --- Endpoints (all /me routes, JWT-protected) ---

@router.patch("/me", response_model=UserResponse)
async def update_me(
    data: UserUpdateRequest,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if data.telegram_chat_id is not None:
        user.telegram_chat_id = data.telegram_chat_id
    if data.push_token is not None:
        user.push_token = data.push_token
    if data.preferred_zone is not None:
        user.preferred_zone = data.preferred_zone

    await db.flush()
    await db.refresh(user)
    return user


# --- Watchlist ---

@router.get("/me/watchlist", response_model=list[WatchlistItemResponse])
async def get_watchlist(
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserWatchlist)
        .options(joinedload(UserWatchlist.product))
        .where(UserWatchlist.user_id == user.id)
    )
    items = result.unique().scalars().all()

    today = date.today()
    response = []
    for item in items:
        offer_result = await db.execute(
            select(Offer)
            .options(joinedload(Offer.chain))
            .where(
                Offer.product_id == item.product_id,
                Offer.valid_from <= today,
                Offer.valid_to >= today,
            )
            .order_by(Offer.offer_price)
            .limit(1)
        )
        best = offer_result.unique().scalar_one_or_none()

        response.append(
            WatchlistItemResponse(
                id=item.id,
                product_id=item.product_id,
                product_name=item.product.name if item.product else "Unknown",
                brand=item.product.brand if item.product else None,
                target_price=item.target_price,
                notify_any_offer=item.notify_any_offer,
                best_current_price=best.offer_price if best else None,
                best_chain=best.chain.name if best and best.chain else None,
            )
        )
    return response


@router.post("/me/watchlist", response_model=WatchlistItemResponse, status_code=201)
async def add_to_watchlist(
    data: WatchlistAddRequest,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Check product exists
    prod_result = await db.execute(
        select(Product).where(Product.id == data.product_id)
    )
    product = prod_result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Check duplicate
    existing = await db.execute(
        select(UserWatchlist).where(
            UserWatchlist.user_id == user.id,
            UserWatchlist.product_id == data.product_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Product already in watchlist")

    entry = UserWatchlist(
        user_id=user.id,
        product_id=data.product_id,
        target_price=data.target_price,
        notify_any_offer=data.notify_any_offer,
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)

    return WatchlistItemResponse(
        id=entry.id,
        product_id=entry.product_id,
        product_name=product.name,
        brand=product.brand,
        target_price=entry.target_price,
        notify_any_offer=entry.notify_any_offer,
    )


@router.get("/me/watchlist/ids")
async def get_watchlist_ids(
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return just the product IDs in the user's watchlist (lightweight)."""
    result = await db.execute(
        select(UserWatchlist.product_id).where(UserWatchlist.user_id == user.id)
    )
    product_ids = [str(row[0]) for row in result.all()]
    return {"product_ids": product_ids}


@router.delete("/me/watchlist/{product_id}", status_code=204)
async def remove_from_watchlist(
    product_id: uuid.UUID,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserWatchlist).where(
            UserWatchlist.user_id == user.id,
            UserWatchlist.product_id == product_id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Watchlist entry not found")
    await db.delete(entry)


# --- User Stores ---

@router.post("/me/stores", status_code=201)
async def add_user_store(
    data: StoreAddRequest,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_store = UserStore(user_id=user.id, store_id=data.store_id)
    db.add(user_store)
    await db.flush()
    return {"status": "ok"}


# --- User Deals ---

@router.get("/me/deals", response_model=list[UserDealResponse])
async def get_user_deals(
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get personalized deals for products in user's watchlist."""
    today = date.today()

    wl_result = await db.execute(
        select(UserWatchlist.product_id).where(UserWatchlist.user_id == user.id)
    )
    product_ids = [row[0] for row in wl_result.all()]

    if not product_ids:
        return []

    offers_result = await db.execute(
        select(Offer)
        .options(joinedload(Offer.product), joinedload(Offer.chain))
        .where(
            Offer.product_id.in_(product_ids),
            Offer.valid_from <= today,
            Offer.valid_to >= today,
        )
        .order_by(Offer.discount_pct.desc().nulls_last(), Offer.offer_price)
    )
    offers = offers_result.unique().scalars().all()

    return [
        UserDealResponse(
            product_id=str(o.product_id),
            product_name=o.product.name if o.product else "Unknown",
            brand=o.product.brand if o.product else None,
            chain_name=o.chain.name if o.chain else "Unknown",
            offer_price=o.offer_price,
            original_price=o.original_price,
            discount_pct=o.discount_pct,
            valid_to=o.valid_to,
            image_url=o.product.image_url if o.product else None,
        )
        for o in offers
    ]


# --- User Brands ---

@router.get("/me/brands", response_model=list[UserBrandResponse])
async def get_user_brands(
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserBrand)
        .where(UserBrand.user_id == user.id)
        .order_by(UserBrand.brand_name)
    )
    return result.scalars().all()


@router.post("/me/brands", response_model=UserBrandResponse, status_code=201)
async def add_user_brand(
    data: BrandAddRequest,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(
        select(UserBrand).where(
            UserBrand.user_id == user.id,
            UserBrand.brand_name == data.brand_name,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Brand already saved")

    entry = UserBrand(
        user_id=user.id,
        brand_name=data.brand_name,
        category=data.category,
        notify=data.notify,
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return entry


@router.delete("/me/brands/{brand_id}", status_code=204)
async def remove_user_brand(
    brand_id: uuid.UUID,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserBrand).where(
            UserBrand.id == brand_id,
            UserBrand.user_id == user.id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Brand not found")
    await db.delete(entry)


# --- Suggested Alternatives ---

@router.get("/me/alternatives", response_model=list[AlternativeResponse])
async def get_alternatives(
    limit: int = 20,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Suggest cheaper alternatives in categories the user watches."""
    today = date.today()

    # Get watchlist product IDs and their categories
    wl_result = await db.execute(
        select(UserWatchlist.product_id).where(UserWatchlist.user_id == user.id)
    )
    wl_product_ids = [row[0] for row in wl_result.all()]
    if not wl_product_ids:
        return []

    cat_result = await db.execute(
        select(Product.category).where(
            Product.id.in_(wl_product_ids),
            Product.category.isnot(None),
        ).distinct()
    )
    categories = [row[0] for row in cat_result.all()]
    if not categories:
        return []

    # Find active offers in those categories, excluding watchlist products
    stmt = (
        select(Offer)
        .options(joinedload(Offer.product), joinedload(Offer.chain))
        .join(Product, Offer.product_id == Product.id)
        .where(
            Product.category.in_(categories),
            Offer.product_id.notin_(wl_product_ids),
            Offer.valid_from <= today,
            Offer.valid_to >= today,
        )
        .order_by(Offer.price_per_unit.asc().nulls_last(), Offer.offer_price.asc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    offers = result.unique().scalars().all()

    return [
        AlternativeResponse(
            product_id=str(o.product_id),
            product_name=o.product.name if o.product else "Unknown",
            brand=o.product.brand if o.product else None,
            category=o.product.category if o.product else None,
            chain_name=o.chain.name if o.chain else "Unknown",
            offer_price=o.offer_price,
            original_price=o.original_price,
            discount_pct=o.discount_pct,
            price_per_unit=o.price_per_unit,
            unit_reference=o.unit_reference,
            valid_to=o.valid_to,
            image_url=o.product.image_url if o.product else None,
        )
        for o in offers
    ]


# --- Brand Deals ---

@router.get("/me/brand-deals", response_model=list[BrandDealResponse])
async def get_brand_deals(
    limit: int = 30,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get active offers for the user's favourite brands."""
    today = date.today()

    brands_result = await db.execute(
        select(UserBrand).where(UserBrand.user_id == user.id)
    )
    user_brands = brands_result.scalars().all()
    if not user_brands:
        return []

    # Build OR conditions for each brand
    from sqlalchemy import or_

    brand_conditions = []
    for ub in user_brands:
        cond = Product.brand.ilike(f"%{ub.brand_name}%")
        if ub.category:
            cond = (cond) & (Product.category.ilike(ub.category))
        brand_conditions.append(cond)

    stmt = (
        select(Offer)
        .options(joinedload(Offer.product), joinedload(Offer.chain))
        .join(Product, Offer.product_id == Product.id)
        .where(
            or_(*brand_conditions),
            Offer.valid_from <= today,
            Offer.valid_to >= today,
        )
        .order_by(Offer.discount_pct.desc().nulls_last())
        .limit(limit)
    )
    result = await db.execute(stmt)
    offers = result.unique().scalars().all()

    return [
        BrandDealResponse(
            product_id=str(o.product_id),
            product_name=o.product.name if o.product else "Unknown",
            brand=o.product.brand if o.product else None,
            category=o.product.category if o.product else None,
            chain_name=o.chain.name if o.chain else "Unknown",
            offer_price=o.offer_price,
            original_price=o.original_price,
            discount_pct=o.discount_pct,
            price_per_unit=o.price_per_unit,
            unit_reference=o.unit_reference,
            valid_to=o.valid_to,
            image_url=o.product.image_url if o.product else None,
        )
        for o in offers
    ]
