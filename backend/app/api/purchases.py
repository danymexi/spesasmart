"""Purchase history API endpoints."""

import asyncio
import logging
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.auth import get_current_user
from app.database import get_db
from app.models.purchase import (
    PurchaseItem,
    PurchaseOrder,
    PurchaseSyncLog,
    SupermarketCredential,
)
from app.models.user import UserProfile
from app.services.credential_encryption import decrypt, encrypt, mask_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users/me", tags=["purchases"])

SUPPORTED_CHAINS = {"esselunga", "iperal"}
RECEIPT_CHAINS = {"esselunga", "iperal", "coop", "lidl", "carrefour", "conad", "eurospin", "aldi", "md", "penny", "pam"}

RECEIPTS_DIR = Path("/app/receipts")
try:
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    # In test/dev environments /app may not be writable
    RECEIPTS_DIR = Path("/tmp/receipts")
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)


# ── Schemas ──────────────────────────────────────────────────────────────────

class SupermarketAccountCreate(BaseModel):
    chain_slug: str
    email: str
    password: str


class SupermarketAccountResponse(BaseModel):
    chain_slug: str
    masked_email: str
    is_valid: bool
    last_error: str | None
    last_synced_at: str | None
    session_status: str  # "active" | "expired" | "missing"


class PurchaseOrderResponse(BaseModel):
    id: str
    chain_slug: str
    external_order_id: str
    order_date: str
    total_amount: float | None
    store_name: str | None
    status: str | None
    items_count: int
    has_receipt: bool = False
    source: str | None = None


class PurchaseOrderUpdate(BaseModel):
    chain_slug: str | None = None


class PurchaseItemResponse(BaseModel):
    id: str
    external_name: str
    external_code: str | None
    quantity: float | None
    unit_price: float | None
    total_price: float | None
    brand: str | None
    category: str | None
    product_id: str | None
    product_name: str | None


class SyncResponse(BaseModel):
    status: str
    message: str


class ReceiptItemResponse(BaseModel):
    name: str
    quantity: float
    unit_price: str | None
    total_price: str
    discount: str | None
    category: str | None
    product_id: str | None = None
    product_name: str | None = None


class ReceiptUploadResponse(BaseModel):
    order_id: str
    store_name: str | None
    date: str | None
    total: str | None
    items_count: int
    items: list[ReceiptItemResponse]
    skipped: bool = False


# ── Supermarket accounts ─────────────────────────────────────────────────────

@router.post("/supermarket-accounts", response_model=SupermarketAccountResponse)
async def create_supermarket_account(
    body: SupermarketAccountCreate,
    background_tasks: BackgroundTasks,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save encrypted supermarket credentials and trigger first sync."""
    if body.chain_slug not in SUPPORTED_CHAINS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported chain: {body.chain_slug}. Supported: {', '.join(SUPPORTED_CHAINS)}",
        )

    # Check if credentials already exist for this user+chain
    result = await db.execute(
        select(SupermarketCredential).where(
            SupermarketCredential.user_id == user.id,
            SupermarketCredential.chain_slug == body.chain_slug,
        )
    )
    existing = result.scalar_one_or_none()

    encrypted_email = encrypt(body.email)
    encrypted_password = encrypt(body.password)

    if existing:
        existing.encrypted_email = encrypted_email
        existing.encrypted_password = encrypted_password
        existing.is_valid = True
        existing.last_error = None
        existing.updated_at = datetime.now(timezone.utc)
    else:
        cred = SupermarketCredential(
            user_id=user.id,
            chain_slug=body.chain_slug,
            encrypted_email=encrypted_email,
            encrypted_password=encrypted_password,
        )
        db.add(cred)

    await db.commit()

    # Trigger initial sync in background
    background_tasks.add_task(_run_sync, user.id, body.chain_slug)

    return SupermarketAccountResponse(
        chain_slug=body.chain_slug,
        masked_email=mask_email(body.email),
        is_valid=True,
        last_error=None,
        last_synced_at=None,
        session_status="missing",
    )


@router.get("/supermarket-accounts", response_model=list[SupermarketAccountResponse])
async def list_supermarket_accounts(
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List connected supermarket accounts (email masked)."""
    result = await db.execute(
        select(SupermarketCredential).where(
            SupermarketCredential.user_id == user.id
        )
    )
    creds = result.scalars().all()

    accounts = []
    for cred in creds:
        masked = "—"
        if cred.encrypted_email:
            try:
                email = decrypt(cred.encrypted_email)
                masked = mask_email(email)
            except Exception:
                masked = "***"

        # Determine session status
        if cred.encrypted_session:
            if cred.session_expires_at and cred.session_expires_at < datetime.now(timezone.utc):
                sess_status = "expired"
            elif cred.is_valid:
                sess_status = "active"
            else:
                sess_status = "expired"
        else:
            sess_status = "missing"

        accounts.append(SupermarketAccountResponse(
            chain_slug=cred.chain_slug,
            masked_email=masked,
            is_valid=cred.is_valid,
            last_error=cred.last_error,
            last_synced_at=cred.last_synced_at.isoformat() if cred.last_synced_at else None,
            session_status=sess_status,
        ))

    return accounts


@router.delete("/supermarket-accounts/{chain_slug}")
async def delete_supermarket_account(
    chain_slug: str,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Disconnect a supermarket account and delete all associated data."""
    result = await db.execute(
        select(SupermarketCredential).where(
            SupermarketCredential.user_id == user.id,
            SupermarketCredential.chain_slug == chain_slug,
        )
    )
    cred = result.scalar_one_or_none()
    if not cred:
        raise HTTPException(status_code=404, detail="Account not found.")

    # Delete credentials
    await db.delete(cred)

    # Delete orders for this chain
    orders_result = await db.execute(
        select(PurchaseOrder).where(
            PurchaseOrder.user_id == user.id,
            PurchaseOrder.chain_slug == chain_slug,
        )
    )
    for order in orders_result.scalars().all():
        await db.delete(order)

    # Delete sync logs
    logs_result = await db.execute(
        select(PurchaseSyncLog).where(
            PurchaseSyncLog.user_id == user.id,
            PurchaseSyncLog.chain_slug == chain_slug,
        )
    )
    for log in logs_result.scalars().all():
        await db.delete(log)

    await db.commit()
    return {"detail": "Account disconnected."}


@router.post("/supermarket-accounts/{chain_slug}/sync", response_model=SyncResponse)
async def trigger_sync(
    chain_slug: str,
    background_tasks: BackgroundTasks,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger a manual sync for a specific chain."""
    result = await db.execute(
        select(SupermarketCredential).where(
            SupermarketCredential.user_id == user.id,
            SupermarketCredential.chain_slug == chain_slug,
        )
    )
    cred = result.scalar_one_or_none()
    if not cred:
        raise HTTPException(status_code=404, detail="Account not found.")

    background_tasks.add_task(_run_sync, user.id, chain_slug)
    return SyncResponse(status="started", message="Sync avviato in background.")


# ── Session-based auth ───────────────────────────────────────────────────────

@router.post("/supermarket-accounts/{chain_slug}/session", response_model=SupermarketAccountResponse)
async def upload_session(
    chain_slug: str,
    session_data: dict,
    background_tasks: BackgroundTasks,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a Playwright storageState JSON as session for a supermarket chain."""
    if chain_slug not in SUPPORTED_CHAINS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported chain: {chain_slug}. Supported: {', '.join(SUPPORTED_CHAINS)}",
        )

    import json
    encrypted = encrypt(json.dumps(session_data))

    result = await db.execute(
        select(SupermarketCredential).where(
            SupermarketCredential.user_id == user.id,
            SupermarketCredential.chain_slug == chain_slug,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.encrypted_session = encrypted
        existing.is_valid = True
        existing.last_error = None
        existing.updated_at = datetime.now(timezone.utc)
    else:
        cred = SupermarketCredential(
            user_id=user.id,
            chain_slug=chain_slug,
            encrypted_session=encrypted,
        )
        db.add(cred)

    await db.commit()

    # Trigger initial sync in background
    background_tasks.add_task(_run_sync, user.id, chain_slug)

    return SupermarketAccountResponse(
        chain_slug=chain_slug,
        masked_email="—",
        is_valid=True,
        last_error=None,
        last_synced_at=None,
        session_status="active",
    )


@router.get("/supermarket-accounts/{chain_slug}/session-status")
async def get_session_status(
    chain_slug: str,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check session status for a specific chain."""
    result = await db.execute(
        select(SupermarketCredential).where(
            SupermarketCredential.user_id == user.id,
            SupermarketCredential.chain_slug == chain_slug,
        )
    )
    cred = result.scalar_one_or_none()
    if not cred:
        return {"status": "missing", "detail": "Account non collegato."}

    if cred.encrypted_session:
        if cred.session_expires_at and cred.session_expires_at < datetime.now(timezone.utc):
            return {"status": "expired", "detail": "Sessione scaduta — riesegui il login manuale."}
        if cred.is_valid:
            return {"status": "active", "detail": "Sessione attiva."}
        return {"status": "expired", "detail": cred.last_error or "Sessione non valida."}

    if cred.encrypted_email:
        if cred.is_valid:
            return {"status": "active", "detail": "Credenziali attive."}
        return {"status": "expired", "detail": cred.last_error or "Credenziali non valide."}

    return {"status": "missing", "detail": "Nessuna sessione o credenziale trovata."}


# ── Receipt upload (OCR) ─────────────────────────────────────────────────────

@router.post("/purchases/upload-receipt", response_model=ReceiptUploadResponse)
async def upload_receipt(
    file: UploadFile = File(...),
    chain_slug: str = Form(...),
    external_receipt_id: str | None = Form(None),
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a receipt photo for OCR extraction via Gemini Vision."""
    # Dedup: if external_receipt_id provided, check for existing order
    if external_receipt_id:
        dedup_ext_id = f"receipt-{external_receipt_id}"
        existing_result = await db.execute(
            select(PurchaseOrder).where(
                PurchaseOrder.user_id == user.id,
                PurchaseOrder.chain_slug == chain_slug,
                PurchaseOrder.external_order_id == dedup_ext_id,
            )
        )
        existing_order = existing_result.scalar_one_or_none()
        if existing_order:
            return ReceiptUploadResponse(
                order_id=str(existing_order.id),
                store_name=existing_order.store_name,
                date=existing_order.order_date.isoformat() if existing_order.order_date else None,
                total=str(existing_order.total_amount) if existing_order.total_amount else None,
                items_count=0,
                items=[],
                skipped=True,
            )

    if chain_slug not in RECEIPT_CHAINS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Catena non supportata: {chain_slug}. Supportate: {', '.join(sorted(RECEIPT_CHAINS))}",
        )

    # Validate file type
    content_type = file.content_type or ""
    is_pdf = content_type == "application/pdf" or (file.filename or "").lower().endswith(".pdf")
    if not content_type.startswith("image/") and not is_pdf:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Il file deve essere un'immagine (JPEG, PNG, WebP) o un PDF.",
        )

    # Determine file extension
    if is_pdf:
        suffix = ".pdf"
    elif "png" in content_type:
        suffix = ".png"
    elif "webp" in content_type:
        suffix = ".webp"
    else:
        suffix = ".jpg"

    # Save to temp file for OCR processing
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        contents = await file.read()
        tmp.write(contents)
        tmp_path = Path(tmp.name)

    try:
        from app.services.receipt_ocr import parse_receipt_image, _parse_italian_price

        result = await parse_receipt_image(tmp_path, chain_slug)

        if "error" in result and not result.get("items"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=result.get("error", "Impossibile leggere lo scontrino."),
            )

        # Parse the receipt date
        receipt_date = datetime.now(timezone.utc)
        if result.get("date"):
            try:
                receipt_date = datetime.fromisoformat(result["date"]).replace(tzinfo=timezone.utc)
            except ValueError:
                pass

        # Parse total
        total_amount = _parse_italian_price(result.get("total"))

        # Create PurchaseOrder
        order_id = uuid.uuid4()

        # Save receipt file persistently
        receipt_filename = f"{order_id}{suffix}"
        user_receipts_dir = RECEIPTS_DIR / str(user.id)
        user_receipts_dir.mkdir(parents=True, exist_ok=True)
        receipt_path = user_receipts_dir / receipt_filename
        shutil.copy2(str(tmp_path), str(receipt_path))

        ext_order_id = f"receipt-{external_receipt_id}" if external_receipt_id else f"receipt-{order_id.hex[:12]}"

        order = PurchaseOrder(
            id=order_id,
            user_id=user.id,
            chain_slug=chain_slug,
            external_order_id=ext_order_id,
            order_date=receipt_date,
            total_amount=total_amount,
            store_name=result.get("store_name"),
            status="completed",
            raw_data={
                "source": "receipt_upload",
                "receipt_filename": receipt_filename,
                "ocr_result": result,
            },
        )
        db.add(order)

        # Create PurchaseItems
        items_response = []
        for item_data in result.get("items", []):
            name = (item_data.get("name") or "").strip()
            if not name:
                continue

            quantity = Decimal("1")
            try:
                q = item_data.get("quantity")
                if q is not None:
                    quantity = Decimal(str(q))
            except (InvalidOperation, ValueError, TypeError):
                pass

            unit_price = _parse_italian_price(item_data.get("unit_price"))
            total_price = _parse_italian_price(item_data.get("total_price"))

            purchase_item = PurchaseItem(
                order_id=order_id,
                external_name=name,
                quantity=quantity,
                unit_price=unit_price,
                total_price=total_price,
                brand=None,
                category=item_data.get("category"),
            )
            db.add(purchase_item)

            # Try to match to a catalog product
            matched_product_id = None
            matched_product_name = None
            try:
                from app.services.product_matcher import ProductMatcher
                matcher = ProductMatcher()
                product = await matcher.create_or_match_product({
                    "name": name,
                    "category": item_data.get("category"),
                })
                purchase_item.product_id = product.id
                matched_product_id = str(product.id)
                matched_product_name = product.name
            except Exception:
                logger.debug("Product matching failed for '%s', skipping", name)

            items_response.append(ReceiptItemResponse(
                name=name,
                quantity=float(quantity),
                unit_price=item_data.get("unit_price"),
                total_price=item_data.get("total_price", "0"),
                discount=item_data.get("discount"),
                category=item_data.get("category"),
                product_id=matched_product_id,
                product_name=matched_product_name,
            ))

        await db.commit()

        return ReceiptUploadResponse(
            order_id=str(order_id),
            store_name=result.get("store_name"),
            date=result.get("date"),
            total=result.get("total"),
            items_count=len(items_response),
            items=items_response,
        )

    finally:
        # Clean up temp file
        try:
            tmp_path.unlink()
        except OSError:
            pass


# ── Receipt file & order management ──────────────────────────────────────

@router.get("/purchases/{order_id}/receipt")
async def get_receipt_file(
    order_id: str,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Serve the stored receipt file (image or PDF)."""
    result = await db.execute(
        select(PurchaseOrder).where(
            PurchaseOrder.id == uuid.UUID(order_id),
            PurchaseOrder.user_id == user.id,
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")

    raw = order.raw_data or {}
    receipt_filename = raw.get("receipt_filename")
    if not receipt_filename:
        raise HTTPException(status_code=404, detail="Nessuno scontrino salvato per questo ordine.")

    receipt_path = RECEIPTS_DIR / str(user.id) / receipt_filename
    if not receipt_path.exists():
        raise HTTPException(status_code=404, detail="File scontrino non trovato.")

    # Determine media type
    suffix = receipt_path.suffix.lower()
    media_types = {
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".webp": "image/webp",
    }
    media_type = media_types.get(suffix, "application/octet-stream")

    return FileResponse(receipt_path, media_type=media_type, filename=receipt_filename)


@router.patch("/purchases/{order_id}", response_model=PurchaseOrderResponse)
async def update_purchase_order(
    order_id: str,
    body: PurchaseOrderUpdate,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a purchase order (e.g. change chain_slug)."""
    result = await db.execute(
        select(PurchaseOrder).where(
            PurchaseOrder.id == uuid.UUID(order_id),
            PurchaseOrder.user_id == user.id,
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")

    if body.chain_slug is not None:
        if body.chain_slug not in RECEIPT_CHAINS:
            raise HTTPException(
                status_code=400,
                detail=f"Catena non supportata: {body.chain_slug}",
            )
        order.chain_slug = body.chain_slug

    await db.commit()
    await db.refresh(order)

    count_result = await db.execute(
        select(func.count()).where(PurchaseItem.order_id == order.id)
    )
    items_count = count_result.scalar() or 0

    raw = order.raw_data or {}
    return PurchaseOrderResponse(
        id=str(order.id),
        chain_slug=order.chain_slug,
        external_order_id=order.external_order_id,
        order_date=order.order_date.isoformat(),
        total_amount=float(order.total_amount) if order.total_amount else None,
        store_name=order.store_name,
        status=order.status,
        items_count=items_count,
        has_receipt=bool(raw.get("receipt_filename")),
        source=raw.get("source"),
    )


# ── Purchase history ─────────────────────────────────────────────────────────

@router.get("/purchases", response_model=list[PurchaseOrderResponse])
async def list_purchases(
    limit: int = 50,
    offset: int = 0,
    chain: str | None = None,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List purchase orders (paginated, newest first)."""
    stmt = (
        select(PurchaseOrder)
        .where(PurchaseOrder.user_id == user.id)
        .order_by(PurchaseOrder.order_date.desc())
        .offset(offset)
        .limit(limit)
    )
    if chain:
        stmt = stmt.where(PurchaseOrder.chain_slug == chain)

    result = await db.execute(stmt)
    orders = result.scalars().all()

    response = []
    for order in orders:
        # Count items
        count_result = await db.execute(
            select(func.count()).where(PurchaseItem.order_id == order.id)
        )
        items_count = count_result.scalar() or 0

        raw = order.raw_data or {}
        response.append(PurchaseOrderResponse(
            id=str(order.id),
            chain_slug=order.chain_slug,
            external_order_id=order.external_order_id,
            order_date=order.order_date.isoformat(),
            total_amount=float(order.total_amount) if order.total_amount else None,
            store_name=order.store_name,
            status=order.status,
            items_count=items_count,
            has_receipt=bool(raw.get("receipt_filename")),
            source=raw.get("source"),
        ))

    return response


@router.get("/purchases/{order_id}/items", response_model=list[PurchaseItemResponse])
async def get_purchase_items(
    order_id: str,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get items for a specific purchase order."""
    # Verify order belongs to user
    result = await db.execute(
        select(PurchaseOrder).where(
            PurchaseOrder.id == uuid.UUID(order_id),
            PurchaseOrder.user_id == user.id,
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")

    items_result = await db.execute(
        select(PurchaseItem)
        .where(PurchaseItem.order_id == order.id)
        .order_by(PurchaseItem.external_name)
    )
    items = items_result.scalars().all()

    response = []
    for item in items:
        # Get matched product name if available
        product_name = None
        if item.product_id:
            from app.models.product import Product
            prod_result = await db.execute(
                select(Product.name).where(Product.id == item.product_id)
            )
            product_name = prod_result.scalar_one_or_none()

        response.append(PurchaseItemResponse(
            id=str(item.id),
            external_name=item.external_name,
            external_code=item.external_code,
            quantity=float(item.quantity) if item.quantity else None,
            unit_price=float(item.unit_price) if item.unit_price else None,
            total_price=float(item.total_price) if item.total_price else None,
            brand=item.brand,
            category=item.category,
            product_id=str(item.product_id) if item.product_id else None,
            product_name=product_name,
        ))

    return response


# ── Backfill products ────────────────────────────────────────────────────────

@router.post("/purchases/backfill-products")
async def backfill_products(
    user: UserProfile = Depends(get_current_user),
):
    """Match unmatched receipt items to catalog products."""
    from app.services.backfill_receipt_products import backfill_unmatched_receipt_items
    result = await backfill_unmatched_receipt_items(user.id)
    return result


# ── Habits & Smart List ──────────────────────────────────────────────────────

@router.get("/purchase-habits")
async def get_purchase_habits(
    user: UserProfile = Depends(get_current_user),
):
    """Analyze purchase habits: frequency, avg price, next predicted purchase."""
    from app.services.purchase_analyzer import compute_habits
    return await compute_habits(user.id)


@router.get("/smart-list")
async def get_smart_list(
    user: UserProfile = Depends(get_current_user),
):
    """Generate a smart shopping list based on purchase patterns."""
    from app.services.purchase_analyzer import generate_smart_list
    return await generate_smart_list(user.id)


# ── Smart List → Watchlist sync ───────────────────────────────────────────────

class SyncWatchlistRequest(BaseModel):
    product_ids: list[str]


@router.post("/smart-list/sync-watchlist")
async def sync_smart_list_to_watchlist(
    body: SyncWatchlistRequest,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add smart list products to the user's watchlist (skip duplicates)."""
    from app.models.user import UserWatchlist

    added = 0
    for pid_str in body.product_ids:
        try:
            pid = uuid.UUID(pid_str)
        except ValueError:
            continue

        # Check for existing entry
        existing = await db.execute(
            select(UserWatchlist).where(
                UserWatchlist.user_id == user.id,
                UserWatchlist.product_id == pid,
            )
        )
        if existing.scalar_one_or_none():
            continue

        entry = UserWatchlist(
            user_id=user.id,
            product_id=pid,
            notify_any_offer=True,
        )
        db.add(entry)
        added += 1

    if added > 0:
        await db.commit()

    return {"added": added, "total_requested": len(body.product_ids)}


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _run_sync(user_id: uuid.UUID, chain_slug: str) -> None:
    """Background task wrapper for purchase sync."""
    try:
        from app.services.purchase_sync import PurchaseSyncService
        result = await PurchaseSyncService.sync_user_chain(user_id, chain_slug)
        logger.info("Purchase sync completed for user=%s chain=%s: %s", user_id, chain_slug, result)
    except Exception:
        logger.exception("Purchase sync failed for user=%s chain=%s", user_id, chain_slug)
