"""API routes for supermarket chains."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Chain

router = APIRouter(prefix="/chains", tags=["chains"])


class ChainResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    logo_url: str | None
    website_url: str | None

    model_config = {"from_attributes": True}


@router.get("", response_model=list[ChainResponse])
async def list_chains(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Chain).order_by(Chain.name))
    return result.scalars().all()


@router.get("/{chain_id}", response_model=ChainResponse)
async def get_chain(chain_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Chain).where(Chain.id == chain_id))
    chain = result.scalar_one_or_none()
    if not chain:
        raise HTTPException(status_code=404, detail="Chain not found")
    return chain
