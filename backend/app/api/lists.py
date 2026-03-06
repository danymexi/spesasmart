"""API routes for shopping lists (multiple lists per user)."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func as sql_func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import ShoppingList, ShoppingListItem, UserProfile

router = APIRouter(prefix="/lists", tags=["lists"])


# --- Schemas ---

class ListCreateRequest(BaseModel):
    name: str = "La mia lista"
    emoji: str = "🛒"


class ListUpdateRequest(BaseModel):
    name: str | None = None
    emoji: str | None = None
    is_archived: bool | None = None


class ListResponse(BaseModel):
    id: uuid.UUID
    name: str
    emoji: str
    is_archived: bool
    item_count: int = 0
    unchecked_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ListDuplicateRequest(BaseModel):
    name: str | None = None


# --- Endpoints ---

@router.get("", response_model=list[ListResponse])
async def get_lists(
    include_archived: bool = Query(False),
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all shopping lists for the current user."""
    query = (
        select(
            ShoppingList,
            sql_func.count(ShoppingListItem.id).label("item_count"),
            sql_func.count(
                sql_func.nullif(ShoppingListItem.checked, True)
            ).label("unchecked_count"),
        )
        .outerjoin(ShoppingListItem, ShoppingList.id == ShoppingListItem.list_id)
        .where(ShoppingList.user_id == user.id)
        .group_by(ShoppingList.id)
        .order_by(ShoppingList.updated_at.desc())
    )
    if not include_archived:
        query = query.where(ShoppingList.is_archived.is_(False))

    result = await db.execute(query)
    rows = result.all()

    return [
        ListResponse(
            id=sl.id,
            name=sl.name,
            emoji=sl.emoji,
            is_archived=sl.is_archived,
            item_count=item_count,
            unchecked_count=unchecked_count,
            created_at=sl.created_at,
            updated_at=sl.updated_at,
        )
        for sl, item_count, unchecked_count in rows
    ]


@router.post("", response_model=ListResponse, status_code=201)
async def create_list(
    data: ListCreateRequest,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new shopping list."""
    sl = ShoppingList(
        user_id=user.id,
        name=data.name,
        emoji=data.emoji,
    )
    db.add(sl)
    await db.flush()
    await db.refresh(sl)

    return ListResponse(
        id=sl.id,
        name=sl.name,
        emoji=sl.emoji,
        is_archived=sl.is_archived,
        item_count=0,
        unchecked_count=0,
        created_at=sl.created_at,
        updated_at=sl.updated_at,
    )


@router.get("/{list_id}", response_model=ListResponse)
async def get_list(
    list_id: uuid.UUID,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific shopping list."""
    result = await db.execute(
        select(
            ShoppingList,
            sql_func.count(ShoppingListItem.id).label("item_count"),
            sql_func.count(
                sql_func.nullif(ShoppingListItem.checked, True)
            ).label("unchecked_count"),
        )
        .outerjoin(ShoppingListItem, ShoppingList.id == ShoppingListItem.list_id)
        .where(ShoppingList.id == list_id, ShoppingList.user_id == user.id)
        .group_by(ShoppingList.id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Lista non trovata")

    sl, item_count, unchecked_count = row
    return ListResponse(
        id=sl.id,
        name=sl.name,
        emoji=sl.emoji,
        is_archived=sl.is_archived,
        item_count=item_count,
        unchecked_count=unchecked_count,
        created_at=sl.created_at,
        updated_at=sl.updated_at,
    )


@router.put("/{list_id}", response_model=ListResponse)
async def update_list(
    list_id: uuid.UUID,
    data: ListUpdateRequest,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a shopping list."""
    sl = await db.get(ShoppingList, list_id)
    if not sl or sl.user_id != user.id:
        raise HTTPException(status_code=404, detail="Lista non trovata")

    if data.name is not None:
        sl.name = data.name
    if data.emoji is not None:
        sl.emoji = data.emoji
    if data.is_archived is not None:
        sl.is_archived = data.is_archived
    sl.updated_at = datetime.now(timezone.utc)
    await db.flush()

    # Get counts
    count_result = await db.execute(
        select(
            sql_func.count(ShoppingListItem.id),
            sql_func.count(sql_func.nullif(ShoppingListItem.checked, True)),
        ).where(ShoppingListItem.list_id == list_id)
    )
    item_count, unchecked_count = count_result.one()

    return ListResponse(
        id=sl.id,
        name=sl.name,
        emoji=sl.emoji,
        is_archived=sl.is_archived,
        item_count=item_count,
        unchecked_count=unchecked_count,
        created_at=sl.created_at,
        updated_at=sl.updated_at,
    )


@router.delete("/{list_id}", status_code=204)
async def delete_list(
    list_id: uuid.UUID,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a shopping list and all its items."""
    sl = await db.get(ShoppingList, list_id)
    if not sl or sl.user_id != user.id:
        raise HTTPException(status_code=404, detail="Lista non trovata")

    await db.delete(sl)


@router.post("/{list_id}/duplicate", response_model=ListResponse, status_code=201)
async def duplicate_list(
    list_id: uuid.UUID,
    data: ListDuplicateRequest | None = None,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Duplicate a shopping list with all its items (unchecked)."""
    sl = await db.get(ShoppingList, list_id)
    if not sl or sl.user_id != user.id:
        raise HTTPException(status_code=404, detail="Lista non trovata")

    new_name = (data.name if data and data.name else f"{sl.name} (copia)")
    new_list = ShoppingList(
        user_id=user.id,
        name=new_name,
        emoji=sl.emoji,
    )
    db.add(new_list)
    await db.flush()

    # Copy items
    items_result = await db.execute(
        select(ShoppingListItem).where(ShoppingListItem.list_id == list_id)
    )
    items = items_result.scalars().all()
    for item in items:
        new_item = ShoppingListItem(
            user_id=user.id,
            list_id=new_list.id,
            product_id=item.product_id,
            custom_name=item.custom_name,
            quantity=item.quantity,
            unit=item.unit,
            checked=False,
            notes=item.notes,
        )
        db.add(new_item)

    await db.flush()
    await db.refresh(new_list)

    return ListResponse(
        id=new_list.id,
        name=new_list.name,
        emoji=new_list.emoji,
        is_archived=new_list.is_archived,
        item_count=len(items),
        unchecked_count=len(items),
        created_at=new_list.created_at,
        updated_at=new_list.updated_at,
    )


@router.post("/{list_id}/clear-checked", status_code=200)
async def clear_checked_items(
    list_id: uuid.UUID,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove all checked items from a list."""
    sl = await db.get(ShoppingList, list_id)
    if not sl or sl.user_id != user.id:
        raise HTTPException(status_code=404, detail="Lista non trovata")

    result = await db.execute(
        select(ShoppingListItem).where(
            ShoppingListItem.list_id == list_id,
            ShoppingListItem.checked.is_(True),
        )
    )
    checked_items = result.scalars().all()
    for item in checked_items:
        await db.delete(item)

    return {"cleared": len(checked_items)}
