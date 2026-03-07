"""Auth API routes: register, login, guest, claim, google, me."""

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_access_token, get_current_user, hash_password, verify_password
from app.database import get_db
from app.models.user import UserProfile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# --- Schemas ---

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ClaimRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str | None
    preferred_zone: str
    is_guest: bool = False
    is_admin: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    access_token: str
    user: UserResponse


# --- Endpoints ---

@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    # Check if email already exists
    result = await db.execute(
        select(UserProfile).where(UserProfile.email == data.email)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    if len(data.password) < 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password must be at least 6 characters")

    user = UserProfile(
        email=data.email,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    token = create_access_token(str(user.id), user.email)
    return AuthResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.post("/login", response_model=AuthResponse)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(UserProfile).where(UserProfile.email == data.email)
    )
    user = result.scalar_one_or_none()
    if not user or not user.password_hash or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    token = create_access_token(str(user.id), user.email)
    return AuthResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
async def me(user: UserProfile = Depends(get_current_user)):
    return user


@router.post("/guest", response_model=AuthResponse, status_code=201)
async def create_guest(db: AsyncSession = Depends(get_db)):
    """Create an anonymous guest account and return a JWT."""
    user = UserProfile(is_guest=True)
    db.add(user)
    await db.flush()
    await db.refresh(user)

    token = create_access_token(str(user.id), "")
    return AuthResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.post("/claim", response_model=AuthResponse)
async def claim_guest(
    data: ClaimRequest,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Convert a guest account to a full account with email and password."""
    if not user.is_guest:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account is already registered",
        )

    # Check email uniqueness
    existing = await db.execute(
        select(UserProfile).where(UserProfile.email == data.email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    if len(data.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 6 characters",
        )

    user.email = data.email
    user.password_hash = hash_password(data.password)
    user.is_guest = False
    await db.flush()
    await db.refresh(user)

    token = create_access_token(str(user.id), user.email)
    return AuthResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


class GoogleAuthRequest(BaseModel):
    id_token: str


@router.post("/google", response_model=AuthResponse)
async def google_auth(
    data: GoogleAuthRequest,
    db: AsyncSession = Depends(get_db),
):
    """Verify a Google id_token, find or create user, return JWT."""
    try:
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests

        from app.config import get_settings
        settings = get_settings()

        idinfo = google_id_token.verify_oauth2_token(
            data.id_token,
            google_requests.Request(),
            settings.google_client_id,
        )
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google auth not configured (google-auth package missing)",
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token",
        )

    google_id = idinfo["sub"]
    email = idinfo.get("email")

    # Find existing user by google_id
    result = await db.execute(
        select(UserProfile).where(UserProfile.google_id == google_id)
    )
    user = result.scalar_one_or_none()

    if user is None and email:
        # Check if user exists by email (link accounts)
        result = await db.execute(
            select(UserProfile).where(UserProfile.email == email)
        )
        user = result.scalar_one_or_none()
        if user:
            user.google_id = google_id
            user.auth_provider = "google"

    if user is None:
        # Create new user
        user = UserProfile(
            email=email,
            google_id=google_id,
            auth_provider="google",
        )
        db.add(user)

    await db.flush()
    await db.refresh(user)

    token = create_access_token(str(user.id), user.email or "")
    return AuthResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )
