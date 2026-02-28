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
from app.models import Offer, Product, UserProfile, UserStore, UserWatchlist

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
    product_name: str
    brand: str | None
    chain_name: str
    offer_price: Decimal
    original_price: Decimal | None
    discount_pct: Decimal | None
    valid_to: date | None


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
        .order_by(Offer.offer_price)
    )
    offers = offers_result.unique().scalars().all()

    return [
        UserDealResponse(
            product_name=o.product.name if o.product else "Unknown",
            brand=o.product.brand if o.product else None,
            chain_name=o.chain.name if o.chain else "Unknown",
            offer_price=o.offer_price,
            original_price=o.original_price,
            discount_pct=o.discount_pct,
            valid_to=o.valid_to,
        )
        for o in offers
    ]
