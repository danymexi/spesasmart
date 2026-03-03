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
from app.models import Chain, Offer, Product, ShoppingListItem, UserBrand, UserProfile, UserStore, UserWatchlist

router = APIRouter(prefix="/users", tags=["users"])


# --- Schemas ---

class UserResponse(BaseModel):
    id: uuid.UUID
    email: str | None
    telegram_chat_id: int | None
    push_token: str | None
    preferred_zone: str
    notification_mode: str = "instant"
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdateRequest(BaseModel):
    telegram_chat_id: int | None = None
    push_token: str | None = None
    preferred_zone: str | None = None
    notification_mode: str | None = None


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


class ShoppingListAddRequest(BaseModel):
    product_id: uuid.UUID | None = None
    custom_name: str | None = None
    quantity: int = 1
    unit: str | None = None
    offer_id: uuid.UUID | None = None
    notes: str | None = None


class ShoppingListItemResponse(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID | None
    product_name: str | None
    custom_name: str | None
    quantity: int
    unit: str | None
    checked: bool
    offer_id: uuid.UUID | None
    chain_name: str | None
    offer_price: Decimal | None
    notes: str | None
    created_at: datetime


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
    if data.notification_mode is not None:
        if data.notification_mode not in ("instant", "digest"):
            raise HTTPException(status_code=400, detail="notification_mode must be 'instant' or 'digest'")
        user.notification_mode = data.notification_mode

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


# --- Preferred Chains ---

class PreferredChainsRequest(BaseModel):
    chains: list[str]


@router.get("/me/preferred-chains")
async def get_preferred_chains(
    user: UserProfile = Depends(get_current_user),
):
    """Return the user's preferred chain slugs."""
    if user.preferred_chains:
        chains = [c.strip() for c in user.preferred_chains.split(",") if c.strip()]
    else:
        chains = []
    return {"chains": chains}


@router.put("/me/preferred-chains")
async def update_preferred_chains(
    data: PreferredChainsRequest,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Set the user's preferred chain slugs."""
    valid_slugs = {"esselunga", "lidl", "coop", "iperal"}
    filtered = [c for c in data.chains if c in valid_slugs]
    user.preferred_chains = ",".join(filtered) if filtered else None
    await db.flush()
    return {"chains": filtered}


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
    """Get personalized deals for products in user's watchlist.

    Also finds similar products (same brand + similar name) across chains
    so the user sees a full multi-chain comparison.
    """
    today = date.today()

    wl_result = await db.execute(
        select(UserWatchlist.product_id).where(UserWatchlist.user_id == user.id)
    )
    watchlist_ids = [row[0] for row in wl_result.all()]

    if not watchlist_ids:
        return []

    # Fetch watchlist products to find similar ones
    from app.api.products import (
        _normalize_product_name, _names_match, SequenceMatcher,
    )

    prod_result = await db.execute(
        select(Product).where(Product.id.in_(watchlist_ids))
    )
    watchlist_products = list(prod_result.scalars().all())

    # For each watchlist product, find similar products across ALL chains
    all_product_ids = set(watchlist_ids)
    similar_to_watchlist: dict = {}

    if watchlist_products:
        # Build name search patterns from watchlist products
        name_patterns = []
        for wp in watchlist_products:
            # Use first significant word (>=4 chars) as ILIKE search term
            words = wp.name.split()
            for w in words:
                if len(w) >= 4 and w.lower() not in ("alla", "allo", "alle", "della", "dello", "delle", "con", "per"):
                    name_patterns.append(w)
                    break

        if name_patterns:
            from sqlalchemy import or_
            candidates_result = await db.execute(
                select(Product).where(
                    or_(*[Product.name.ilike(f"%{pat}%") for pat in name_patterns]),
                    Product.id.notin_(watchlist_ids),
                )
            )
            candidates = list(candidates_result.scalars().all())

            for wp in watchlist_products:
                wp_norm = _normalize_product_name(wp.name)
                wp_brand = (wp.brand or "").lower().strip()
                for cp in candidates:
                    if cp.id in similar_to_watchlist:
                        continue
                    cp_norm = _normalize_product_name(cp.name)
                    if not _names_match(wp_norm, cp_norm, threshold=0.80):
                        continue
                    shorter, longer = sorted([wp_norm, cp_norm], key=len)
                    # Require name to be at least 50% of longer name
                    if len(longer) > 0 and len(shorter) / len(longer) < 0.5:
                        continue
                    cp_brand = (cp.brand or "").lower().strip()
                    if wp_brand and cp_brand and wp_brand != cp_brand:
                        # Short/generic names require same brand
                        if len(shorter.split()) < 3:
                            continue
                        ratio = SequenceMatcher(None, wp_norm, cp_norm).ratio()
                        if not (ratio >= 0.85 or (len(shorter) >= 6 and shorter in longer)):
                            continue
                    all_product_ids.add(cp.id)
                    similar_to_watchlist[cp.id] = wp.id

    # Fetch all active offers for watchlist + similar products
    offers_result = await db.execute(
        select(Offer)
        .options(joinedload(Offer.product), joinedload(Offer.chain))
        .where(
            Offer.product_id.in_(list(all_product_ids)),
            Offer.valid_from <= today,
            Offer.valid_to >= today,
        )
        .order_by(Offer.discount_pct.desc().nulls_last(), Offer.offer_price)
    )
    offers = offers_result.unique().scalars().all()

    # Map similar product offers to their watchlist product_id.
    # Keep only the BEST offer per (mapped_product, chain) to avoid
    # flooding the card with dozens of prices.
    best_per_chain: dict[tuple, Offer] = {}  # (mapped_pid, chain_name) -> best offer
    for o in offers:
        mapped_pid = similar_to_watchlist.get(o.product_id, o.product_id)
        chain_name = o.chain.name if o.chain else "Unknown"
        key = (mapped_pid, chain_name)
        existing = best_per_chain.get(key)
        if existing is None or o.offer_price < existing.offer_price:
            best_per_chain[key] = o

    results = []
    for (mapped_pid, chain_name), o in best_per_chain.items():
        wp = next((p for p in watchlist_products if p.id == mapped_pid), None)
        results.append(
            UserDealResponse(
                product_id=str(mapped_pid),
                product_name=wp.name if wp else (o.product.name if o.product else "Unknown"),
                brand=wp.brand if wp else (o.product.brand if o.product else None),
                chain_name=chain_name,
                offer_price=o.offer_price,
                original_price=o.original_price,
                discount_pct=o.discount_pct,
                valid_to=o.valid_to,
                image_url=wp.image_url if wp and wp.image_url else (o.product.image_url if o.product else None),
            )
        )

    # Sort by product then price so frontend groups correctly
    results.sort(key=lambda r: (r.product_id, r.offer_price))
    return results


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


# --- Shopping List ---

@router.get("/me/shopping-list", response_model=list[ShoppingListItemResponse])
async def get_shopping_list(
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the user's shopping list with product/offer details."""
    result = await db.execute(
        select(ShoppingListItem)
        .options(
            joinedload(ShoppingListItem.product),
            joinedload(ShoppingListItem.offer).joinedload(Offer.chain),
        )
        .where(ShoppingListItem.user_id == user.id)
        .order_by(ShoppingListItem.checked, ShoppingListItem.created_at.desc())
    )
    items = result.unique().scalars().all()

    return [
        ShoppingListItemResponse(
            id=item.id,
            product_id=item.product_id,
            product_name=item.product.name if item.product else None,
            custom_name=item.custom_name,
            quantity=item.quantity,
            unit=item.unit,
            checked=item.checked,
            offer_id=item.offer_id,
            chain_name=item.offer.chain.name if item.offer and item.offer.chain else None,
            offer_price=item.offer.offer_price if item.offer else None,
            notes=item.notes,
            created_at=item.created_at,
        )
        for item in items
    ]


@router.get("/me/shopping-list/count")
async def get_shopping_list_count(
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the count of unchecked items in the shopping list."""
    from sqlalchemy import func as sql_func

    result = await db.execute(
        select(sql_func.count(ShoppingListItem.id)).where(
            ShoppingListItem.user_id == user.id,
            ShoppingListItem.checked.is_(False),
        )
    )
    count = result.scalar() or 0
    return {"count": count}


@router.post("/me/shopping-list", response_model=ShoppingListItemResponse, status_code=201)
async def add_to_shopping_list(
    data: ShoppingListAddRequest,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add an item to the shopping list."""
    if not data.product_id and not data.custom_name:
        raise HTTPException(status_code=400, detail="Either product_id or custom_name is required")

    product_name = None
    if data.product_id:
        prod = await db.execute(select(Product).where(Product.id == data.product_id))
        product = prod.scalar_one_or_none()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        product_name = product.name

    chain_name = None
    offer_price = None
    if data.offer_id:
        offer_res = await db.execute(
            select(Offer).options(joinedload(Offer.chain)).where(Offer.id == data.offer_id)
        )
        offer = offer_res.unique().scalar_one_or_none()
        if offer:
            chain_name = offer.chain.name if offer.chain else None
            offer_price = offer.offer_price

    item = ShoppingListItem(
        user_id=user.id,
        product_id=data.product_id,
        custom_name=data.custom_name,
        quantity=data.quantity,
        unit=data.unit,
        offer_id=data.offer_id,
        notes=data.notes,
    )
    db.add(item)
    await db.flush()
    await db.refresh(item)

    return ShoppingListItemResponse(
        id=item.id,
        product_id=item.product_id,
        product_name=product_name,
        custom_name=item.custom_name,
        quantity=item.quantity,
        unit=item.unit,
        checked=item.checked,
        offer_id=item.offer_id,
        chain_name=chain_name,
        offer_price=offer_price,
        notes=item.notes,
        created_at=item.created_at,
    )


@router.patch("/me/shopping-list/{item_id}/check")
async def toggle_shopping_item(
    item_id: uuid.UUID,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggle the checked state of a shopping list item."""
    result = await db.execute(
        select(ShoppingListItem).where(
            ShoppingListItem.id == item_id,
            ShoppingListItem.user_id == user.id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    item.checked = not item.checked
    await db.flush()
    return {"id": str(item.id), "checked": item.checked}


@router.delete("/me/shopping-list/checked", status_code=204)
async def clear_checked_items(
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove all checked items from the shopping list."""
    from sqlalchemy import delete as sql_delete

    await db.execute(
        sql_delete(ShoppingListItem).where(
            ShoppingListItem.user_id == user.id,
            ShoppingListItem.checked.is_(True),
        )
    )


@router.delete("/me/shopping-list/{item_id}", status_code=204)
async def remove_shopping_item(
    item_id: uuid.UUID,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a single item from the shopping list."""
    result = await db.execute(
        select(ShoppingListItem).where(
            ShoppingListItem.id == item_id,
            ShoppingListItem.user_id == user.id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    await db.delete(item)


# --- Trip Optimizer ---

class TripItemResponse(BaseModel):
    product_name: str
    offer_price: Decimal
    chain_name: str


class StoreTripResponse(BaseModel):
    chain_name: str
    items: list[TripItemResponse]
    total: Decimal


class TripOptimizationResponse(BaseModel):
    single_store_best: StoreTripResponse | None
    multi_store_plan: list[StoreTripResponse]
    single_store_total: Decimal
    multi_store_total: Decimal
    potential_savings: Decimal


@router.get("/me/shopping-list/optimize", response_model=TripOptimizationResponse)
async def optimize_shopping_trip(
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Analyse the shopping list and suggest optimal purchasing strategies."""
    from app.services.trip_optimizer import TripOptimizer

    optimizer = TripOptimizer()
    result = await optimizer.optimize(user.id, db)

    def _convert_trip(trip) -> StoreTripResponse:
        return StoreTripResponse(
            chain_name=trip.chain_name,
            items=[
                TripItemResponse(
                    product_name=i.product_name,
                    offer_price=i.offer_price,
                    chain_name=i.chain_name,
                )
                for i in trip.items
            ],
            total=trip.total,
        )

    return TripOptimizationResponse(
        single_store_best=_convert_trip(result.single_store_best) if result.single_store_best else None,
        multi_store_plan=[_convert_trip(t) for t in result.multi_store_plan],
        single_store_total=result.single_store_total,
        multi_store_total=result.multi_store_total,
        potential_savings=result.potential_savings,
    )
