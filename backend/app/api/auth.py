"""Auth API routes: register, login, guest, claim, google, me."""

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_access_token, create_refresh_token, get_current_user, hash_password, verify_password
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
    refresh_token: str | None = None
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
    refresh = create_refresh_token(str(user.id))
    return AuthResponse(
        access_token=token,
        refresh_token=refresh,
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
    refresh = create_refresh_token(str(user.id))
    return AuthResponse(
        access_token=token,
        refresh_token=refresh,
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
    refresh = create_refresh_token(str(user.id))
    return AuthResponse(
        access_token=token,
        refresh_token=refresh,
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
    refresh = create_refresh_token(str(user.id))
    return AuthResponse(
        access_token=token,
        refresh_token=refresh,
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
    refresh = create_refresh_token(str(user.id))
    return AuthResponse(
        access_token=token,
        refresh_token=refresh,
        user=UserResponse.model_validate(user),
    )


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/refresh", response_model=AuthResponse)
async def refresh_token(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Exchange a valid refresh token for a new access + refresh token pair."""
    from jose import JWTError, jwt as jose_jwt
    from app.config import get_settings

    settings = get_settings()
    try:
        payload = jose_jwt.decode(
            data.refresh_token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    result = await db.execute(select(UserProfile).where(UserProfile.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    new_access = create_access_token(str(user.id), user.email or "")
    new_refresh = create_refresh_token(str(user.id))
    return AuthResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        user=UserResponse.model_validate(user),
    )


# ── Password Reset ────────────────────────────────────────────────────────────

def _create_reset_token(user_id: str, email: str) -> str:
    """Create a short-lived reset token (1 hour)."""
    from datetime import timedelta, timezone, datetime
    from jose import jwt as jose_jwt
    from app.config import get_settings

    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(hours=1)
    payload = {
        "sub": user_id,
        "email": email,
        "type": "reset",
        "exp": expire,
    }
    return jose_jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


@router.post("/forgot-password")
async def forgot_password(data: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Generate a password reset token. Always returns 200 to prevent email enumeration."""
    result = await db.execute(
        select(UserProfile).where(UserProfile.email == data.email)
    )
    user = result.scalar_one_or_none()
    if user:
        token = _create_reset_token(str(user.id), user.email)
        # Log the token (no email sending for now)
        logger.info("Password reset token for %s: %s", data.email, token)

    return {"message": "If this email is registered, a reset link has been generated. Check server logs."}


@router.post("/reset-password", response_model=AuthResponse)
async def reset_password(data: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Validate a reset token and set a new password."""
    from jose import JWTError, jwt as jose_jwt
    from app.config import get_settings

    if len(data.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    settings = get_settings()
    try:
        payload = jose_jwt.decode(
            data.token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        if payload.get("type") != "reset":
            raise HTTPException(status_code=400, detail="Invalid token type")
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=400, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    result = await db.execute(select(UserProfile).where(UserProfile.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid token")

    user.password_hash = hash_password(data.new_password)
    await db.flush()
    await db.refresh(user)

    access = create_access_token(str(user.id), user.email or "")
    refresh = create_refresh_token(str(user.id))
    return AuthResponse(
        access_token=access,
        refresh_token=refresh,
        user=UserResponse.model_validate(user),
    )
