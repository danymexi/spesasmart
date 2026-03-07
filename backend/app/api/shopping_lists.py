"""API routes for multiple shopping lists — CRUD, sharing, duplication."""

import json
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, update, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.auth import get_current_user, get_optional_user
from app.config import get_settings
from app.database import get_db
from app.models import Offer, Product, ShoppingList, ShoppingListItem, ShoppingListItemProduct, UserProfile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["shopping-lists"])

# Also mount a top-level router for public /shared/ routes
shared_router = APIRouter(tags=["shared-lists"])


# ── Schemas ─────────────────────────────────────────────────────────────────

class ShoppingListCreate(BaseModel):
    name: str = "Spesa"
    emoji: str | None = None
    color: str | None = None


class ShoppingListUpdate(BaseModel):
    name: str | None = None
    emoji: str | None = None
    color: str | None = None
    is_archived: bool | None = None
    is_template: bool | None = None


class ShoppingListResponse(BaseModel):
    id: uuid.UUID
    name: str
    emoji: str | None
    color: str | None
    is_archived: bool
    is_template: bool
    sort_order: int
    item_count: int = 0
    unchecked_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReorderRequest(BaseModel):
    list_ids: list[uuid.UUID]


class ShareResponse(BaseModel):
    share_url: str
    token: str
    expires_at: datetime


class SharedListItemResponse(BaseModel):
    product_name: str | None
    custom_name: str | None
    quantity: int
    unit: str | None
    checked: bool


class SharedListResponse(BaseModel):
    name: str
    emoji: str | None
    color: str | None
    items: list[SharedListItemResponse]


class ItemReorderRequest(BaseModel):
    item_ids: list[uuid.UUID]


# ── Helper ──────────────────────────────────────────────────────────────────

async def _get_or_create_default_list(user: UserProfile, db: AsyncSession) -> ShoppingList:
    """Return the user's first non-archived list, creating one if none exists."""
    result = await db.execute(
        select(ShoppingList)
        .where(ShoppingList.user_id == user.id, ShoppingList.is_archived.is_(False))
        .order_by(ShoppingList.sort_order, ShoppingList.created_at)
        .limit(1)
    )
    sl = result.scalar_one_or_none()
    if sl:
        return sl

    sl = ShoppingList(user_id=user.id, name="Spesa", sort_order=0)
    db.add(sl)
    await db.flush()
    await db.refresh(sl)
    return sl


def _list_response(sl: ShoppingList, items: list | None = None) -> ShoppingListResponse:
    all_items = items if items is not None else (sl.items if hasattr(sl, "items") and sl.items is not None else [])
    return ShoppingListResponse(
        id=sl.id,
        name=sl.name,
        emoji=sl.emoji,
        color=sl.color,
        is_archived=sl.is_archived,
        is_template=sl.is_template,
        sort_order=sl.sort_order,
        item_count=len(all_items),
        unchecked_count=sum(1 for i in all_items if not i.checked),
        created_at=sl.created_at,
        updated_at=sl.updated_at,
    )


# ── List CRUD ───────────────────────────────────────────────────────────────

@router.get("/me/lists", response_model=list[ShoppingListResponse])
async def get_lists(
    include_archived: bool = False,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """All user's lists with item counts."""
    q = (
        select(ShoppingList)
        .options(joinedload(ShoppingList.items))
        .where(ShoppingList.user_id == user.id)
        .order_by(ShoppingList.sort_order, ShoppingList.created_at)
    )
    if not include_archived:
        q = q.where(ShoppingList.is_archived.is_(False))

    result = await db.execute(q)
    lists = result.unique().scalars().all()

    # Auto-create a default list if the user has none
    if not lists:
        default = await _get_or_create_default_list(user, db)
        lists = [default]

    return [_list_response(sl) for sl in lists]


@router.post("/me/lists", response_model=ShoppingListResponse, status_code=201)
async def create_list(
    data: ShoppingListCreate,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new shopping list."""
    # Find highest sort_order
    result = await db.execute(
        select(ShoppingList.sort_order)
        .where(ShoppingList.user_id == user.id)
        .order_by(ShoppingList.sort_order.desc())
        .limit(1)
    )
    max_order = result.scalar() or 0

    sl = ShoppingList(
        user_id=user.id,
        name=data.name,
        emoji=data.emoji,
        color=data.color,
        sort_order=max_order + 1,
    )
    db.add(sl)
    await db.flush()
    await db.refresh(sl)
    return _list_response(sl, items=[])


@router.get("/me/lists/{list_id}", response_model=ShoppingListResponse)
async def get_list(
    list_id: uuid.UUID,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Single list with item counts."""
    result = await db.execute(
        select(ShoppingList)
        .options(joinedload(ShoppingList.items))
        .where(ShoppingList.id == list_id, ShoppingList.user_id == user.id)
    )
    sl = result.unique().scalar_one_or_none()
    if not sl:
        raise HTTPException(status_code=404, detail="List not found")
    return _list_response(sl)


@router.patch("/me/lists/{list_id}", response_model=ShoppingListResponse)
async def update_list(
    list_id: uuid.UUID,
    data: ShoppingListUpdate,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update list metadata."""
    result = await db.execute(
        select(ShoppingList)
        .options(joinedload(ShoppingList.items))
        .where(ShoppingList.id == list_id, ShoppingList.user_id == user.id)
    )
    sl = result.unique().scalar_one_or_none()
    if not sl:
        raise HTTPException(status_code=404, detail="List not found")

    if data.name is not None:
        sl.name = data.name
    if data.emoji is not None:
        sl.emoji = data.emoji
    if data.color is not None:
        sl.color = data.color
    if data.is_archived is not None:
        sl.is_archived = data.is_archived
    if data.is_template is not None:
        sl.is_template = data.is_template

    await db.flush()
    await db.refresh(sl)
    return _list_response(sl)


@router.delete("/me/lists/{list_id}", status_code=204)
async def delete_list(
    list_id: uuid.UUID,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a list and all its items."""
    result = await db.execute(
        select(ShoppingList).where(
            ShoppingList.id == list_id, ShoppingList.user_id == user.id
        )
    )
    sl = result.scalar_one_or_none()
    if not sl:
        raise HTTPException(status_code=404, detail="List not found")
    await db.delete(sl)


# ── Duplicate ───────────────────────────────────────────────────────────────

@router.post("/me/lists/{list_id}/duplicate", response_model=ShoppingListResponse, status_code=201)
async def duplicate_list(
    list_id: uuid.UUID,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Clone a list with all its items."""
    result = await db.execute(
        select(ShoppingList)
        .options(
            joinedload(ShoppingList.items).joinedload(ShoppingListItem.linked_products),
        )
        .where(ShoppingList.id == list_id, ShoppingList.user_id == user.id)
    )
    src = result.unique().scalar_one_or_none()
    if not src:
        raise HTTPException(status_code=404, detail="List not found")

    # Find max sort_order
    max_q = await db.execute(
        select(ShoppingList.sort_order)
        .where(ShoppingList.user_id == user.id)
        .order_by(ShoppingList.sort_order.desc())
        .limit(1)
    )
    max_order = max_q.scalar() or 0

    new_list = ShoppingList(
        user_id=user.id,
        name=f"{src.name} (copia)",
        emoji=src.emoji,
        color=src.color,
        sort_order=max_order + 1,
    )
    db.add(new_list)
    await db.flush()

    new_items = []
    for item in src.items:
        new_item = ShoppingListItem(
            user_id=user.id,
            list_id=new_list.id,
            product_id=item.product_id,
            custom_name=item.custom_name,
            quantity=item.quantity,
            unit=item.unit,
            checked=False,
            offer_id=item.offer_id,
            notes=item.notes,
            sort_order=item.sort_order,
        )
        db.add(new_item)
        await db.flush()

        for lp in item.linked_products:
            db.add(ShoppingListItemProduct(item_id=new_item.id, product_id=lp.product_id))
        new_items.append(new_item)

    await db.flush()
    await db.refresh(new_list)
    return _list_response(new_list, items=new_items)


# ── Reorder ─────────────────────────────────────────────────────────────────

@router.put("/me/lists/reorder", status_code=200)
async def reorder_lists(
    data: ReorderRequest,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bulk reorder lists."""
    for idx, lid in enumerate(data.list_ids):
        await db.execute(
            update(ShoppingList)
            .where(ShoppingList.id == lid, ShoppingList.user_id == user.id)
            .values(sort_order=idx)
        )
    return {"status": "ok"}


# ── Item reorder ────────────────────────────────────────────────────────────

@router.put("/me/shopping-list/reorder", status_code=200)
async def reorder_items(
    data: ItemReorderRequest,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bulk reorder items within a list."""
    for idx, iid in enumerate(data.item_ids):
        await db.execute(
            update(ShoppingListItem)
            .where(ShoppingListItem.id == iid, ShoppingListItem.user_id == user.id)
            .values(sort_order=idx)
        )
    return {"status": "ok"}


# ── Sharing ─────────────────────────────────────────────────────────────────

@router.post("/me/lists/{list_id}/share", response_model=ShareResponse)
async def share_list(
    list_id: uuid.UUID,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a 24-hour share token."""
    result = await db.execute(
        select(ShoppingList).where(
            ShoppingList.id == list_id, ShoppingList.user_id == user.id
        )
    )
    sl = result.scalar_one_or_none()
    if not sl:
        raise HTTPException(status_code=404, detail="List not found")

    token = secrets.token_urlsafe(48)
    expires = datetime.now(timezone.utc) + timedelta(hours=24)
    sl.share_token = token
    sl.share_expires_at = expires
    await db.flush()

    return ShareResponse(
        share_url=f"/shared/{token}",
        token=token,
        expires_at=expires,
    )


# ── Public shared list routes ───────────────────────────────────────────────

@shared_router.get("/shared/{token}", response_model=SharedListResponse)
async def view_shared_list(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Public: view a shared list (no auth required)."""
    result = await db.execute(
        select(ShoppingList)
        .options(
            joinedload(ShoppingList.items).joinedload(ShoppingListItem.product),
        )
        .where(ShoppingList.share_token == token)
    )
    sl = result.unique().scalar_one_or_none()

    if not sl:
        raise HTTPException(status_code=404, detail="Shared list not found or expired")

    if sl.share_expires_at and sl.share_expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Share link has expired")

    return SharedListResponse(
        name=sl.name,
        emoji=sl.emoji,
        color=sl.color,
        items=[
            SharedListItemResponse(
                product_name=item.product.name if item.product else None,
                custom_name=item.custom_name,
                quantity=item.quantity,
                unit=item.unit,
                checked=item.checked,
            )
            for item in sl.items
        ],
    )


@shared_router.post("/shared/{token}/copy", status_code=201)
async def copy_shared_list(
    token: str,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Copy a shared list to the authenticated user's account."""
    result = await db.execute(
        select(ShoppingList)
        .options(
            joinedload(ShoppingList.items).joinedload(ShoppingListItem.linked_products),
        )
        .where(ShoppingList.share_token == token)
    )
    src = result.unique().scalar_one_or_none()

    if not src:
        raise HTTPException(status_code=404, detail="Shared list not found or expired")
    if src.share_expires_at and src.share_expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Share link has expired")

    # Find max sort_order
    max_q = await db.execute(
        select(ShoppingList.sort_order)
        .where(ShoppingList.user_id == user.id)
        .order_by(ShoppingList.sort_order.desc())
        .limit(1)
    )
    max_order = max_q.scalar() or 0

    new_list = ShoppingList(
        user_id=user.id,
        name=src.name,
        emoji=src.emoji,
        color=src.color,
        sort_order=max_order + 1,
    )
    db.add(new_list)
    await db.flush()

    for item in src.items:
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

        for lp in item.linked_products:
            db.add(ShoppingListItemProduct(item_id=new_item.id, product_id=lp.product_id))

    await db.flush()
    await db.refresh(new_list)
    return {"id": str(new_list.id), "name": new_list.name}


# ── Import from text ──────────────────────────────────────────────────────

class ImportTextRequest(BaseModel):
    text: str


class ParsedItem(BaseModel):
    name: str
    quantity: int = 1
    unit: str | None = None


class ImportedItemResponse(BaseModel):
    name: str
    quantity: int
    unit: str | None
    matched_product_id: str | None
    matched_product_name: str | None


class ImportTextResponse(BaseModel):
    imported: int
    items: list[ImportedItemResponse]


async def _parse_text_with_gemini(text: str) -> list[dict]:
    """Use Gemini to parse free-form grocery text into structured items."""
    settings = get_settings()
    if not settings.gemini_api_key:
        # Fallback: split by newlines/commas
        return _parse_text_simple(text)

    prompt = (
        "Sei un assistente per la spesa. Analizza il seguente testo e restituisci un array JSON "
        "di articoli da comprare. Ogni oggetto deve avere: "
        '"name" (nome del prodotto, in italiano), '
        '"quantity" (numero intero, default 1), '
        '"unit" (unità di misura opzionale: "kg", "g", "l", "ml", "pz", null). '
        "Rispondi SOLO con il JSON array, niente altro.\n\n"
        f"Testo:\n{text}"
    )

    try:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{settings.gemini_model}:generateContent?key={settings.gemini_api_key}"
        )
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.1},
            })
            resp.raise_for_status()
            data = resp.json()

        raw = data["candidates"][0]["content"]["parts"][0]["text"]
        # Strip markdown code fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        items = json.loads(raw)
        if isinstance(items, list):
            return items
    except Exception as e:
        logger.warning("Gemini parse failed, falling back to simple parser: %s", e)

    return _parse_text_simple(text)


def _parse_text_simple(text: str) -> list[dict]:
    """Simple fallback parser: split by newlines/commas, extract quantity."""
    import re

    items = []
    # Split by newlines, commas, or semicolons
    parts = re.split(r"[,;\n]+", text)
    for part in parts:
        part = part.strip().strip("-•*").strip()
        if not part:
            continue

        # Try to extract leading quantity: "2 latte", "3x yogurt", "500g pasta"
        m = re.match(r"^(\d+)\s*[xX]?\s*(.+)$", part)
        if m:
            qty = int(m.group(1))
            name = m.group(2).strip()
            # Check if quantity looks like a weight (e.g., "500g")
            um = re.match(r"^(kg|g|ml|l)\b\s*(.*)", name, re.IGNORECASE)
            if um:
                items.append({"name": um.group(2) or part, "quantity": 1, "unit": f"{qty}{um.group(1)}"})
            else:
                items.append({"name": name, "quantity": max(qty, 1), "unit": None})
        else:
            items.append({"name": part, "quantity": 1, "unit": None})

    return items


async def _fuzzy_match_product(name: str, db: AsyncSession) -> Product | None:
    """Try to match a parsed item name to an existing product in the catalog."""
    words = name.strip().split()
    if not words:
        return None

    # Build ilike conditions: each word must appear in name or brand
    conditions = []
    for word in words:
        pattern = f"%{word}%"
        conditions.append(or_(Product.name.ilike(pattern), Product.brand.ilike(pattern)))

    result = await db.execute(
        select(Product).where(*conditions).limit(5)
    )
    candidates = result.scalars().all()

    if not candidates:
        # Try with just the first two words for broader matching
        if len(words) >= 2:
            pattern = f"%{words[0]}%"
            result = await db.execute(
                select(Product).where(Product.name.ilike(pattern)).limit(10)
            )
            candidates = result.scalars().all()

    if not candidates:
        return None

    # Simple scoring: prefer exact substring match
    name_lower = name.lower()
    best = None
    best_score = 0
    for p in candidates:
        score = 0
        p_name = (p.name or "").lower()
        if name_lower in p_name or p_name in name_lower:
            score += 50
        # Count matching words
        for w in words:
            if w.lower() in p_name:
                score += 10
        if score > best_score:
            best_score = score
            best = p

    return best if best_score >= 10 else None


@router.post("/me/lists/{list_id}/import", response_model=ImportTextResponse)
async def import_text_to_list(
    list_id: uuid.UUID,
    data: ImportTextRequest,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Import items from free-form text (e.g. 'latte, pane, 2 yogurt') into a list."""
    # Verify list ownership
    result = await db.execute(
        select(ShoppingList).where(
            ShoppingList.id == list_id, ShoppingList.user_id == user.id
        )
    )
    sl = result.scalar_one_or_none()
    if not sl:
        raise HTTPException(status_code=404, detail="List not found")

    if not data.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    # Parse text into structured items
    parsed = await _parse_text_with_gemini(data.text)

    # Find max sort_order in the list
    max_q = await db.execute(
        select(ShoppingListItem.sort_order)
        .where(ShoppingListItem.list_id == list_id)
        .order_by(ShoppingListItem.sort_order.desc())
        .limit(1)
    )
    max_order = max_q.scalar() or 0

    imported_items: list[ImportedItemResponse] = []

    for idx, item in enumerate(parsed):
        name = item.get("name", "").strip()
        if not name:
            continue

        qty = max(int(item.get("quantity", 1)), 1)
        unit = item.get("unit")

        # Try to fuzzy-match to catalog
        matched = await _fuzzy_match_product(name, db)

        new_item = ShoppingListItem(
            user_id=user.id,
            list_id=list_id,
            product_id=matched.id if matched else None,
            custom_name=name,
            quantity=qty,
            unit=unit,
            sort_order=max_order + idx + 1,
        )
        db.add(new_item)

        imported_items.append(ImportedItemResponse(
            name=name,
            quantity=qty,
            unit=unit,
            matched_product_id=str(matched.id) if matched else None,
            matched_product_name=matched.name if matched else None,
        ))

    await db.flush()

    return ImportTextResponse(imported=len(imported_items), items=imported_items)
