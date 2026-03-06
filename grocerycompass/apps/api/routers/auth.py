import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Response
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from models.user import User, RefreshToken
from schemas.auth import RegisterRequest, LoginRequest, TokenResponse, UserResponse
from schemas.common import ResponseModel

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def create_access_token(user_id: uuid.UUID) -> tuple[str, int]:
    expires_in = settings.access_token_expire_minutes * 60
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": str(user_id), "exp": expire}
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_in


async def get_current_user(
    db: AsyncSession = Depends(get_db),
) -> User:
    # This will be called with token from Authorization header
    # Simplified for now — full implementation will parse Bearer token
    raise HTTPException(status_code=401, detail="Not implemented yet")


@router.post("/register", response_model=ResponseModel[TokenResponse])
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == req.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email già registrata")

    user = User(
        email=req.email,
        password_hash=pwd_context.hash(req.password),
        display_name=req.display_name,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token, expires_in = create_access_token(user.id)

    # Create refresh token
    refresh = RefreshToken(
        user_id=user.id,
        token=str(uuid.uuid4()),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(refresh)
    await db.commit()

    return ResponseModel(data=TokenResponse(
        access_token=token,
        expires_in=expires_in,
    ))


@router.post("/login", response_model=ResponseModel[TokenResponse])
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()

    if not user or not user.password_hash or not pwd_context.verify(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email o password non validi")

    user.last_login = datetime.now(timezone.utc)
    await db.commit()

    token, expires_in = create_access_token(user.id)

    return ResponseModel(data=TokenResponse(
        access_token=token,
        expires_in=expires_in,
    ))


@router.get("/me", response_model=ResponseModel[UserResponse])
async def get_me(user: User = Depends(get_current_user)):
    return ResponseModel(data=UserResponse.model_validate(user))
