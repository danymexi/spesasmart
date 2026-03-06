import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.shopping_list import ShoppingList, ListItem
from models.product import CanonicalProduct
from schemas.lists import (
    ShoppingListCreate, ShoppingListResponse,
    ListItemCreate, ListItemUpdate, ListItemResponse,
)
from schemas.common import ResponseModel

router = APIRouter()


# For now, user_id comes from a query param for dev. Will switch to JWT auth.
@router.get("", response_model=ResponseModel[list[ShoppingListResponse]])
async def get_lists(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(ShoppingList, func.count(ListItem.id).label("item_count"))
        .outerjoin(ListItem, ShoppingList.id == ListItem.list_id)
        .where(ShoppingList.user_id == user_id)
        .where(ShoppingList.is_archived == False)
        .group_by(ShoppingList.id)
        .order_by(ShoppingList.updated_at.desc())
    )
    result = await db.execute(query)
    lists = []
    for sl, item_count in result.all():
        lists.append(ShoppingListResponse(
            id=sl.id,
            name=sl.name,
            emoji=sl.emoji,
            is_archived=sl.is_archived,
            item_count=item_count,
            created_at=sl.created_at,
            updated_at=sl.updated_at,
        ))
    return ResponseModel(data=lists)


@router.post("", response_model=ResponseModel[ShoppingListResponse])
async def create_list(
    user_id: uuid.UUID,
    req: ShoppingListCreate,
    db: AsyncSession = Depends(get_db),
):
    sl = ShoppingList(user_id=user_id, name=req.name, emoji=req.emoji)
    db.add(sl)
    await db.commit()
    await db.refresh(sl)

    return ResponseModel(data=ShoppingListResponse(
        id=sl.id,
        name=sl.name,
        emoji=sl.emoji,
        is_archived=sl.is_archived,
        item_count=0,
        created_at=sl.created_at,
        updated_at=sl.updated_at,
    ))


@router.get("/{list_id}/items", response_model=ResponseModel[list[ListItemResponse]])
async def get_list_items(list_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    query = (
        select(ListItem, CanonicalProduct)
        .outerjoin(CanonicalProduct, ListItem.canonical_product_id == CanonicalProduct.id)
        .where(ListItem.list_id == list_id)
        .order_by(ListItem.sort_order, ListItem.added_at)
    )
    result = await db.execute(query)
    items = []
    for item, product in result.all():
        items.append(ListItemResponse(
            id=item.id,
            canonical_product_id=item.canonical_product_id,
            free_text_name=item.free_text_name,
            product_name=product.name if product else None,
            product_brand=product.brand if product else None,
            product_image=product.image_url if product else None,
            quantity=float(item.quantity),
            unit=item.unit,
            is_checked=item.is_checked,
            note=item.note,
            sort_order=item.sort_order,
            added_at=item.added_at,
        ))
    return ResponseModel(data=items)


@router.post("/{list_id}/items", response_model=ResponseModel[ListItemResponse])
async def add_list_item(
    list_id: uuid.UUID,
    req: ListItemCreate,
    db: AsyncSession = Depends(get_db),
):
    # Verify list exists
    sl = await db.get(ShoppingList, list_id)
    if not sl:
        raise HTTPException(status_code=404, detail="Lista non trovata")

    # Get max sort_order
    max_order = await db.execute(
        select(func.max(ListItem.sort_order)).where(ListItem.list_id == list_id)
    )
    next_order = (max_order.scalar() or 0) + 1

    item = ListItem(
        list_id=list_id,
        canonical_product_id=req.canonical_product_id,
        free_text_name=req.free_text_name,
        quantity=req.quantity,
        unit=req.unit,
        note=req.note,
        sort_order=next_order,
    )
    db.add(item)

    sl.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(item)

    # Get product info if linked
    product = None
    if item.canonical_product_id:
        product = await db.get(CanonicalProduct, item.canonical_product_id)

    return ResponseModel(data=ListItemResponse(
        id=item.id,
        canonical_product_id=item.canonical_product_id,
        free_text_name=item.free_text_name,
        product_name=product.name if product else None,
        product_brand=product.brand if product else None,
        product_image=product.image_url if product else None,
        quantity=float(item.quantity),
        unit=item.unit,
        is_checked=item.is_checked,
        note=item.note,
        sort_order=item.sort_order,
        added_at=item.added_at,
    ))


@router.put("/{list_id}/items/{item_id}", response_model=ResponseModel[ListItemResponse])
async def update_list_item(
    list_id: uuid.UUID,
    item_id: uuid.UUID,
    req: ListItemUpdate,
    db: AsyncSession = Depends(get_db),
):
    item = await db.get(ListItem, item_id)
    if not item or item.list_id != list_id:
        raise HTTPException(status_code=404, detail="Elemento non trovato")

    if req.quantity is not None:
        item.quantity = req.quantity
    if req.unit is not None:
        item.unit = req.unit
    if req.is_checked is not None:
        item.is_checked = req.is_checked
    if req.note is not None:
        item.note = req.note
    if req.sort_order is not None:
        item.sort_order = req.sort_order

    await db.commit()
    await db.refresh(item)

    product = None
    if item.canonical_product_id:
        product = await db.get(CanonicalProduct, item.canonical_product_id)

    return ResponseModel(data=ListItemResponse(
        id=item.id,
        canonical_product_id=item.canonical_product_id,
        free_text_name=item.free_text_name,
        product_name=product.name if product else None,
        product_brand=product.brand if product else None,
        product_image=product.image_url if product else None,
        quantity=float(item.quantity),
        unit=item.unit,
        is_checked=item.is_checked,
        note=item.note,
        sort_order=item.sort_order,
        added_at=item.added_at,
    ))


@router.delete("/{list_id}/items/{item_id}")
async def delete_list_item(
    list_id: uuid.UUID,
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    item = await db.get(ListItem, item_id)
    if not item or item.list_id != list_id:
        raise HTTPException(status_code=404, detail="Elemento non trovato")

    await db.delete(item)
    await db.commit()
    return ResponseModel(data={"deleted": True})
