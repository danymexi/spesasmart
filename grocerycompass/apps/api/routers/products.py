import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from models.product import CanonicalProduct, StoreProduct
from models.store import Store
from models.chain import Chain
from schemas.products import ProductResponse, ProductSearchResponse, StorePriceResponse
from schemas.common import ResponseModel

router = APIRouter()


@router.get("/search", response_model=ResponseModel[ProductSearchResponse])
async def search_products(
    q: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    category: uuid.UUID | None = None,
    has_discount: bool | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(CanonicalProduct)

    if q:
        query = query.where(CanonicalProduct.name.ilike(f"%{q}%"))
    if category:
        query = query.where(CanonicalProduct.category_id == category)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    products = result.scalars().all()

    product_responses = []
    for p in products:
        product_responses.append(ProductResponse(
            id=p.id,
            name=p.name,
            brand=p.brand,
            quantity_value=float(p.quantity_value) if p.quantity_value else None,
            quantity_unit=p.quantity_unit,
            quantity_raw=p.quantity_raw,
            barcode_ean=p.barcode_ean,
            image_url=p.image_url,
            description=p.description,
            tags=p.tags,
        ))

    return ResponseModel(data=ProductSearchResponse(
        products=product_responses,
        total=total,
        page=page,
        per_page=per_page,
        has_next=(page * per_page) < total,
    ))


@router.get("/{product_id}", response_model=ResponseModel[ProductResponse])
async def get_product(
    product_id: uuid.UUID,
    lat: float | None = None,
    lng: float | None = None,
    radius: int = 20,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CanonicalProduct).where(CanonicalProduct.id == product_id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Prodotto non trovato")

    # Get prices from store_products
    prices_query = (
        select(StoreProduct, Store, Chain)
        .join(Store, StoreProduct.store_id == Store.id, isouter=True)
        .join(Chain, StoreProduct.chain_id == Chain.id)
        .where(StoreProduct.canonical_product_id == product_id)
        .where(StoreProduct.in_stock == True)
        .order_by(StoreProduct.price.asc())
    )
    prices_result = await db.execute(prices_query)
    prices = []
    for sp, store, chain in prices_result.all():
        prices.append(StorePriceResponse(
            store_id=store.id if store else sp.chain_id,
            store_name=store.name if store else chain.name,
            chain_slug=chain.slug,
            chain_name=chain.name,
            chain_logo=chain.logo_url,
            price=float(sp.price),
            price_discounted=float(sp.price_discounted) if sp.price_discounted else None,
            discount_label=sp.discount_label,
            price_per_unit=float(sp.price_per_unit) if sp.price_per_unit else None,
            unit_label=sp.unit_label,
            in_stock=sp.in_stock,
            last_scraped=sp.last_scraped,
        ))

    return ResponseModel(data=ProductResponse(
        id=product.id,
        name=product.name,
        brand=product.brand,
        quantity_value=float(product.quantity_value) if product.quantity_value else None,
        quantity_unit=product.quantity_unit,
        quantity_raw=product.quantity_raw,
        barcode_ean=product.barcode_ean,
        image_url=product.image_url,
        description=product.description,
        tags=product.tags,
        prices=prices,
    ))
