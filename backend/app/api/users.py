"""API routes for user profiles, watchlist, and stores (JWT-protected)."""

import uuid
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.auth import get_current_user
from app.database import get_db
from app.models import Chain, Offer, Product, ShoppingList, ShoppingListItem, ShoppingListItemProduct, UserBrand, UserProfile, UserStore, UserWatchlist

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
    product_ids: list[uuid.UUID] | None = None
    custom_name: str | None = None
    quantity: int = 1
    unit: str | None = None
    offer_id: uuid.UUID | None = None
    notes: str | None = None
    list_id: uuid.UUID | None = None


class LinkedProductDetail(BaseModel):
    id: uuid.UUID
    name: str
    brand: str | None = None


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
    linked_product_ids: list[uuid.UUID] = []
    linked_product_count: int = 0
    linked_products_details: list[LinkedProductDetail] = []
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
    list_id: uuid.UUID | None = None,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the user's shopping list with product/offer details.

    If ``list_id`` is omitted the items of the user's first (default) list
    are returned for backward compatibility.
    """
    if list_id is None:
        # Backward compat: find default list
        from app.api.shopping_lists import _get_or_create_default_list
        default = await _get_or_create_default_list(user, db)
        list_id = default.id

    result = await db.execute(
        select(ShoppingListItem)
        .options(
            joinedload(ShoppingListItem.product),
            joinedload(ShoppingListItem.offer).joinedload(Offer.chain),
            joinedload(ShoppingListItem.linked_products).joinedload(ShoppingListItemProduct.product),
        )
        .where(ShoppingListItem.user_id == user.id, ShoppingListItem.list_id == list_id)
        .order_by(ShoppingListItem.checked, ShoppingListItem.sort_order, ShoppingListItem.created_at.desc())
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
            linked_product_ids=[lp.product_id for lp in item.linked_products],
            linked_product_count=len(item.linked_products),
            linked_products_details=[
                LinkedProductDetail(id=lp.product_id, name=lp.product.name, brand=lp.product.brand)
                for lp in item.linked_products if lp.product
            ],
            created_at=item.created_at,
        )
        for item in items
    ]


@router.get("/me/shopping-list/count")
async def get_shopping_list_count(
    list_id: uuid.UUID | None = None,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the count of unchecked items in the shopping list."""
    from sqlalchemy import func as sql_func

    filters = [ShoppingListItem.user_id == user.id, ShoppingListItem.checked.is_(False)]
    if list_id:
        filters.append(ShoppingListItem.list_id == list_id)

    result = await db.execute(
        select(sql_func.count(ShoppingListItem.id)).where(*filters)
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
    if not data.product_id and not data.product_ids and not data.custom_name:
        raise HTTPException(status_code=400, detail="Either product_id, product_ids, or custom_name is required")

    # Resolve list_id (backward compat: default list if omitted)
    resolved_list_id = data.list_id
    if resolved_list_id is None:
        from app.api.shopping_lists import _get_or_create_default_list
        default = await _get_or_create_default_list(user, db)
        resolved_list_id = default.id

    product_name = None
    linked_product_ids: list[uuid.UUID] = []
    linked_details: list[LinkedProductDetail] = []

    if data.product_ids and len(data.product_ids) > 0:
        # Multi-product mode: validate all products exist
        prods_result = await db.execute(
            select(Product).where(Product.id.in_(data.product_ids))
        )
        found_products = {p.id: p for p in prods_result.scalars().all()}
        missing = [pid for pid in data.product_ids if pid not in found_products]
        if missing:
            raise HTTPException(status_code=404, detail=f"Products not found: {missing}")
        # Use first product's name as display name if no custom_name
        first_product = found_products[data.product_ids[0]]
        product_name = first_product.name

        # Create item without product_id (linked via junction table)
        item = ShoppingListItem(
            user_id=user.id,
            list_id=resolved_list_id,
            product_id=None,
            custom_name=data.custom_name or product_name,
            quantity=data.quantity,
            unit=data.unit,
            offer_id=data.offer_id,
            notes=data.notes,
        )
        db.add(item)
        await db.flush()

        # Create junction table entries
        for pid in data.product_ids:
            link = ShoppingListItemProduct(item_id=item.id, product_id=pid)
            db.add(link)
        await db.flush()
        await db.refresh(item)
        linked_product_ids = list(data.product_ids)
        linked_details = [
            LinkedProductDetail(id=pid, name=found_products[pid].name, brand=found_products[pid].brand)
            for pid in data.product_ids if pid in found_products
        ]

    else:
        # Single product or custom_name mode (backward compatible)
        if data.product_id:
            prod = await db.execute(select(Product).where(Product.id == data.product_id))
            product = prod.scalar_one_or_none()
            if not product:
                raise HTTPException(status_code=404, detail="Product not found")
            product_name = product.name

        item = ShoppingListItem(
            user_id=user.id,
            list_id=resolved_list_id,
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
        linked_product_ids=linked_product_ids,
        linked_product_count=len(linked_product_ids),
        linked_products_details=linked_details,
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
    list_id: uuid.UUID | None = None,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove all checked items from the shopping list."""
    from sqlalchemy import delete as sql_delete

    filters = [ShoppingListItem.user_id == user.id, ShoppingListItem.checked.is_(True)]
    if list_id:
        filters.append(ShoppingListItem.list_id == list_id)

    await db.execute(
        sql_delete(ShoppingListItem).where(*filters)
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


class UpdateLinkedProductsRequest(BaseModel):
    product_ids: list[uuid.UUID]


@router.put("/me/shopping-list/{item_id}/products", response_model=ShoppingListItemResponse)
async def update_linked_products(
    item_id: uuid.UUID,
    data: UpdateLinkedProductsRequest,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Replace the linked products for a shopping list item."""
    result = await db.execute(
        select(ShoppingListItem)
        .options(
            joinedload(ShoppingListItem.product),
            joinedload(ShoppingListItem.offer).joinedload(Offer.chain),
            joinedload(ShoppingListItem.linked_products),
        )
        .where(
            ShoppingListItem.id == item_id,
            ShoppingListItem.user_id == user.id,
        )
    )
    item = result.unique().scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    # Validate all product_ids exist
    if data.product_ids:
        prods_result = await db.execute(
            select(Product).where(Product.id.in_(data.product_ids))
        )
        found = {p.id for p in prods_result.scalars().all()}
        missing = [pid for pid in data.product_ids if pid not in found]
        if missing:
            raise HTTPException(status_code=404, detail=f"Products not found: {missing}")

    # Delete existing links
    from sqlalchemy import delete as sql_delete
    await db.execute(
        sql_delete(ShoppingListItemProduct).where(ShoppingListItemProduct.item_id == item.id)
    )

    # Insert new links
    for pid in data.product_ids:
        db.add(ShoppingListItemProduct(item_id=item.id, product_id=pid))
    await db.flush()

    linked_ids = list(data.product_ids)
    # Fetch product details for the new linked products
    product_details = []
    if linked_ids:
        prods = await db.execute(select(Product).where(Product.id.in_(linked_ids)))
        prod_map = {p.id: p for p in prods.scalars().all()}
        product_details = [
            LinkedProductDetail(id=pid, name=prod_map[pid].name, brand=prod_map[pid].brand)
            for pid in linked_ids if pid in prod_map
        ]
    return ShoppingListItemResponse(
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
        linked_product_ids=linked_ids,
        linked_product_count=len(linked_ids),
        linked_products_details=product_details,
        created_at=item.created_at,
    )


# --- Trip Optimizer ---

class TripItemResponse(BaseModel):
    product_name: str
    offer_price: Decimal
    chain_name: str
    search_term: str | None = None


class MissingItemResponse(BaseModel):
    product_name: str
    search_term: str | None = None


class StoreTripResponse(BaseModel):
    chain_name: str
    items: list[TripItemResponse]
    total: Decimal
    items_covered: int = 0
    coverage_pct: float = 0.0
    distance_km: float | None = None


class TripOptimizationResponse(BaseModel):
    single_store_best: StoreTripResponse | None
    multi_store_plan: list[StoreTripResponse]
    single_store_total: Decimal
    multi_store_total: Decimal
    potential_savings: Decimal
    all_single_stores: list[StoreTripResponse] = []
    items_total: int = 0
    items_not_covered: int = 0
    missing_items: list[MissingItemResponse] = []
    travel_cost: Decimal = Decimal("0")


@router.get("/me/shopping-list/optimize", response_model=TripOptimizationResponse)
async def optimize_shopping_trip(
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    list_id: uuid.UUID | None = None,
    max_stores: int = 3,
    radius_km: float = 15.0,
    travel_cost_per_store: Decimal = Decimal("2.00"),
    min_coverage_pct: float = 0.5,
    user_lat: float | None = None,
    user_lon: float | None = None,
):
    """Analyse the shopping list and suggest optimal purchasing strategies."""
    from app.services.trip_optimizer import OptimizationConfig, TripOptimizer

    config = OptimizationConfig(
        max_stores=max(1, min(max_stores, 5)),
        radius_km=max(1.0, min(radius_km, 50.0)),
        travel_cost_per_store=travel_cost_per_store,
        min_coverage_pct=max(0.0, min(min_coverage_pct, 1.0)),
        user_lat=user_lat,
        user_lon=user_lon,
        list_id=list_id,
    )

    optimizer = TripOptimizer()
    result = await optimizer.optimize(user.id, db, config)

    def _convert_trip(trip) -> StoreTripResponse:
        return StoreTripResponse(
            chain_name=trip.chain_name,
            items=[
                TripItemResponse(
                    product_name=i.product_name,
                    offer_price=i.offer_price,
                    chain_name=i.chain_name,
                    search_term=i.search_term,
                )
                for i in trip.items
            ],
            total=trip.total,
            items_covered=trip.items_covered,
            coverage_pct=trip.coverage_pct,
            distance_km=trip.distance_km,
        )

    return TripOptimizationResponse(
        single_store_best=_convert_trip(result.single_store_best) if result.single_store_best else None,
        multi_store_plan=[_convert_trip(t) for t in result.multi_store_plan],
        single_store_total=result.single_store_total,
        multi_store_total=result.multi_store_total,
        potential_savings=result.potential_savings,
        all_single_stores=[_convert_trip(t) for t in result.all_single_stores],
        items_total=result.items_total,
        items_not_covered=result.items_not_covered,
        missing_items=[
            MissingItemResponse(product_name=m.product_name, search_term=m.search_term)
            for m in result.missing_items
        ],
        travel_cost=result.travel_cost,
    )


# --- Shopping List Compare ---

class ChainPriceInfo(BaseModel):
    chain_name: str
    chain_slug: str
    offer_price: Decimal
    original_price: Decimal | None
    discount_pct: Decimal | None
    product_name: str
    is_best: bool = False


class CompareItem(BaseModel):
    item_id: uuid.UUID
    product_id: uuid.UUID | None
    display_name: str
    image_url: str | None
    quantity: int
    search_term: str | None
    chain_prices: list[ChainPriceInfo]


class ChainTotalInfo(BaseModel):
    chain_name: str
    chain_slug: str
    total: Decimal
    items_covered: int


class ShoppingListCompareResponse(BaseModel):
    items: list[CompareItem]
    chain_totals: list[ChainTotalInfo]
    items_total: int
    multi_store_total: Decimal
    potential_savings: Decimal


@router.get("/me/shopping-list/compare", response_model=ShoppingListCompareResponse)
async def compare_shopping_list(
    chain_slugs: str | None = None,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Compare shopping list prices across chains.

    Returns per-item price breakdown and chain totals.
    Optional chain_slugs param (comma-separated) filters to specific chains.
    """
    from app.services.trip_optimizer import TripOptimizer, _normalize_product_name, _names_match

    today = date.today()

    # Parse chain filter
    filter_chain_slugs: set[str] | None = None
    if chain_slugs:
        filter_chain_slugs = {s.strip() for s in chain_slugs.split(",")}

    # Fetch unchecked shopping list items
    sl_result = await db.execute(
        select(ShoppingListItem)
        .options(
            joinedload(ShoppingListItem.product),
            joinedload(ShoppingListItem.linked_products),
        )
        .where(
            ShoppingListItem.user_id == user.id,
            ShoppingListItem.checked.is_(False),
        )
    )
    items = sl_result.unique().scalars().all()

    if not items:
        return ShoppingListCompareResponse(
            items=[], chain_totals=[], items_total=0,
            multi_store_total=Decimal("0"), potential_savings=Decimal("0"),
        )

    # Three buckets: linked (multi-product), single product, custom name
    linked_items = [i for i in items if len(i.linked_products) > 0]
    product_items = [i for i in items if i.product_id is not None and len(i.linked_products) == 0]
    custom_items = [i for i in items if i.product_id is None and len(i.linked_products) == 0 and i.custom_name]

    # Build chain slug -> (id, name) map
    chains_result = await db.execute(select(Chain))
    all_chains = {c.slug: (c.id, c.name) for c in chains_result.scalars().all()}

    # Build offer filter
    offer_where = [Offer.valid_from <= today, Offer.valid_to >= today]
    if filter_chain_slugs:
        valid_chain_ids = [all_chains[s][0] for s in filter_chain_slugs if s in all_chains]
        if valid_chain_ids:
            offer_where.append(Offer.chain_id.in_(valid_chain_ids))

    # --- Product-linked items ---
    # item_id -> chain_slug -> {price, chain_name, chain_slug, original_price, discount_pct, product_name}
    item_prices: dict[uuid.UUID, dict[str, dict]] = defaultdict(dict)

    if product_items:
        product_ids = [i.product_id for i in product_items]
        offers_result = await db.execute(
            select(Offer)
            .options(joinedload(Offer.chain), joinedload(Offer.product))
            .where(Offer.product_id.in_(product_ids), *offer_where)
            .order_by(Offer.offer_price)
        )
        offers = offers_result.unique().scalars().all()

        # Map product_id -> item_id
        pid_to_item: dict[uuid.UUID, uuid.UUID] = {i.product_id: i.id for i in product_items}

        for o in offers:
            item_id = pid_to_item.get(o.product_id)
            if not item_id or not o.chain:
                continue
            slug = o.chain.slug
            if slug not in item_prices[item_id]:
                item_prices[item_id][slug] = {
                    "offer_price": o.offer_price,
                    "chain_name": o.chain.name,
                    "chain_slug": slug,
                    "original_price": o.original_price,
                    "discount_pct": o.discount_pct,
                    "product_name": o.product.name if o.product else "Unknown",
                }

    # --- Linked items (multi-product) ---
    if linked_items:
        all_linked_pids = []
        for i in linked_items:
            for lp in i.linked_products:
                all_linked_pids.append(lp.product_id)

        if all_linked_pids:
            linked_offers_result = await db.execute(
                select(Offer)
                .options(joinedload(Offer.chain), joinedload(Offer.product))
                .where(Offer.product_id.in_(all_linked_pids), *offer_where)
                .order_by(Offer.offer_price)
            )
            linked_offers = linked_offers_result.unique().scalars().all()

            # Build product_id -> list of offers
            pid_offers: dict[uuid.UUID, list] = defaultdict(list)
            for o in linked_offers:
                if o.chain:
                    pid_offers[o.product_id].append(o)

            # For each linked item, find best offer per chain across all linked products
            for item in linked_items:
                linked_pids = [lp.product_id for lp in item.linked_products]
                for pid in linked_pids:
                    for o in pid_offers.get(pid, []):
                        slug = o.chain.slug
                        # Keep cheapest offer per chain across all linked products
                        if slug not in item_prices[item.id] or o.offer_price < item_prices[item.id][slug]["offer_price"]:
                            item_prices[item.id][slug] = {
                                "offer_price": o.offer_price,
                                "chain_name": o.chain.name,
                                "chain_slug": slug,
                                "original_price": o.original_price,
                                "discount_pct": o.discount_pct,
                                "product_name": o.product.name if o.product else "Unknown",
                            }

    # --- Custom-name items ---
    if custom_items:
        optimizer = TripOptimizer()
        custom_price_matrix, custom_labels = await optimizer._resolve_custom_items(
            custom_items, db, today,
        )
        for item in custom_items:
            for chain_name, (price, cname, prod_name) in custom_price_matrix.get(item.id, {}).items():
                # Find slug for this chain
                slug = None
                for s, (cid, cn) in all_chains.items():
                    if cn == chain_name:
                        slug = s
                        break
                if slug and (not filter_chain_slugs or slug in filter_chain_slugs):
                    if slug not in item_prices[item.id]:
                        item_prices[item.id][slug] = {
                            "offer_price": price,
                            "chain_name": chain_name,
                            "chain_slug": slug,
                            "original_price": None,
                            "discount_pct": None,
                            "product_name": prod_name,
                        }

    # --- Build response ---
    compare_items: list[CompareItem] = []
    chain_totals_map: dict[str, dict] = {}  # slug -> {total, items_covered, chain_name}
    multi_store_total = Decimal("0")

    for item in items:
        if item.checked:
            continue

        display_name = item.custom_name or (item.product.name if item.product else "Unknown")
        image_url = item.product.image_url if item.product else None
        search_term = item.custom_name if item.product_id is None else None

        prices = item_prices.get(item.id, {})

        # Find best price for this item
        best_price = min((p["offer_price"] for p in prices.values()), default=None)

        chain_price_list: list[ChainPriceInfo] = []
        for slug, pdata in sorted(prices.items(), key=lambda x: x[1]["offer_price"]):
            is_best = pdata["offer_price"] == best_price
            chain_price_list.append(ChainPriceInfo(
                chain_name=pdata["chain_name"],
                chain_slug=pdata["chain_slug"],
                offer_price=pdata["offer_price"],
                original_price=pdata["original_price"],
                discount_pct=pdata["discount_pct"],
                product_name=pdata["product_name"],
                is_best=is_best,
            ))

            # Accumulate chain totals
            item_cost = pdata["offer_price"] * item.quantity
            if slug not in chain_totals_map:
                chain_totals_map[slug] = {
                    "total": Decimal("0"),
                    "items_covered": 0,
                    "chain_name": pdata["chain_name"],
                }
            chain_totals_map[slug]["total"] += item_cost
            chain_totals_map[slug]["items_covered"] += 1

        # Multi-store: add best price for this item
        if best_price is not None:
            multi_store_total += best_price * item.quantity

        compare_items.append(CompareItem(
            item_id=item.id,
            product_id=item.product_id,
            display_name=display_name,
            image_url=image_url,
            quantity=item.quantity,
            search_term=search_term,
            chain_prices=chain_price_list,
        ))

    # Build chain totals
    chain_totals = sorted(
        [
            ChainTotalInfo(
                chain_name=data["chain_name"],
                chain_slug=slug,
                total=data["total"],
                items_covered=data["items_covered"],
            )
            for slug, data in chain_totals_map.items()
        ],
        key=lambda c: c.total,
    )

    best_single = chain_totals[0].total if chain_totals else Decimal("0")
    savings = best_single - multi_store_total if best_single > multi_store_total else Decimal("0")

    return ShoppingListCompareResponse(
        items=compare_items,
        chain_totals=chain_totals,
        items_total=len(compare_items),
        multi_store_total=multi_store_total,
        potential_savings=savings,
    )


# --- Shopping List Suggestions ---

class SuggestionItem(BaseModel):
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
    image_url: str | None
    suggestion_type: str  # "alternative" or "complementary"


class ShoppingListSuggestionsResponse(BaseModel):
    alternatives: list[SuggestionItem]
    complementary: list[SuggestionItem]


@router.get("/me/shopping-list/suggestions", response_model=ShoppingListSuggestionsResponse)
async def get_shopping_list_suggestions(
    limit: int = 10,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Suggest products based on the shopping list.

    - alternatives: cheaper products in same categories as list items
    - complementary: popular offers in same categories, not already in list
    """
    today = date.today()

    # Fetch shopping list product IDs and categories
    sl_result = await db.execute(
        select(ShoppingListItem)
        .options(joinedload(ShoppingListItem.product))
        .where(
            ShoppingListItem.user_id == user.id,
            ShoppingListItem.checked.is_(False),
        )
    )
    sl_items = sl_result.unique().scalars().all()

    if not sl_items:
        return ShoppingListSuggestionsResponse(alternatives=[], complementary=[])

    sl_product_ids = [i.product_id for i in sl_items if i.product_id]
    categories = set()
    for i in sl_items:
        if i.product and i.product.category:
            categories.add(i.product.category)

    if not categories:
        return ShoppingListSuggestionsResponse(alternatives=[], complementary=[])

    # Alternatives: cheaper products in same categories, not in list
    alt_stmt = (
        select(Offer)
        .options(joinedload(Offer.product), joinedload(Offer.chain))
        .join(Product, Offer.product_id == Product.id)
        .where(
            Product.category.in_(list(categories)),
            Offer.valid_from <= today,
            Offer.valid_to >= today,
        )
        .order_by(Offer.price_per_unit.asc().nulls_last(), Offer.offer_price.asc())
        .limit(limit * 2)
    )
    if sl_product_ids:
        alt_stmt = alt_stmt.where(Offer.product_id.notin_(sl_product_ids))

    alt_result = await db.execute(alt_stmt)
    alt_offers = alt_result.unique().scalars().all()

    # Deduplicate by product_id
    seen_alt: set[uuid.UUID] = set()
    alternatives: list[SuggestionItem] = []
    for o in alt_offers:
        if o.product_id in seen_alt or len(alternatives) >= limit:
            break
        seen_alt.add(o.product_id)
        alternatives.append(SuggestionItem(
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
            image_url=o.product.image_url if o.product else None,
            suggestion_type="alternative",
        ))

    # Complementary: popular offers (high discount) in same categories, not already suggested
    comp_exclude = sl_product_ids + [uuid.UUID(a.product_id) for a in alternatives]
    comp_stmt = (
        select(Offer)
        .options(joinedload(Offer.product), joinedload(Offer.chain))
        .join(Product, Offer.product_id == Product.id)
        .where(
            Product.category.in_(list(categories)),
            Offer.valid_from <= today,
            Offer.valid_to >= today,
        )
        .order_by(Offer.discount_pct.desc().nulls_last())
        .limit(limit * 2)
    )
    if comp_exclude:
        comp_stmt = comp_stmt.where(Offer.product_id.notin_(comp_exclude))

    comp_result = await db.execute(comp_stmt)
    comp_offers = comp_result.unique().scalars().all()

    seen_comp: set[uuid.UUID] = set()
    complementary: list[SuggestionItem] = []
    for o in comp_offers:
        if o.product_id in seen_comp or len(complementary) >= limit:
            break
        seen_comp.add(o.product_id)
        complementary.append(SuggestionItem(
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
            image_url=o.product.image_url if o.product else None,
            suggestion_type="complementary",
        ))

    return ShoppingListSuggestionsResponse(
        alternatives=alternatives,
        complementary=complementary,
    )


# --- User Location ---

class LocationUpdateRequest(BaseModel):
    lat: float
    lon: float


@router.put("/me/location")
async def update_user_location(
    data: LocationUpdateRequest,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save the user's geolocation."""
    user.lat = Decimal(str(data.lat))
    user.lon = Decimal(str(data.lon))
    await db.flush()
    return {"lat": float(user.lat), "lon": float(user.lon)}
