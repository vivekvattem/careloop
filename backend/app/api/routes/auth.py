from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from datetime import datetime, timedelta, timezone
import hashlib
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.auth import get_current_user, require_roles
from app.core.config import settings
from app.core.security import (
    InvalidTokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
)
from app.db.session import get_db
from app.models.notification import NotificationEventType
from app.models.password_reset import PasswordResetToken
from app.models.user import User, UserRole
from app.repositories.user import UserRepository
from app.schemas.auth import AuthResponse, ForgotPasswordRequest, LoginRequest, MessageResponse, ResetPasswordRequest
from app.schemas.user import UserCreate, UserPublic
from app.services.auth import AuthService, DuplicateEmailError
from app.services.notifications import enqueue

router = APIRouter(prefix="/auth", tags=["authentication"])
REFRESH_COOKIE_NAME = "careloop_refresh"


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.environment == "production",
        samesite=settings.cookie_samesite,
        max_age=settings.refresh_token_days * 24 * 60 * 60,
        path=f"{settings.api_prefix}/auth",
    )


@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, db: Session = Depends(get_db)) -> User:
    try:
        return AuthService(db).register_patient(data)
    except DuplicateEmailError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        ) from None


@router.post("/login", response_model=AuthResponse)
def login(data: LoginRequest, response: Response, db: Session = Depends(get_db)) -> AuthResponse:
    user = AuthService(db).authenticate(str(data.email), data.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    _set_refresh_cookie(response, create_refresh_token(user))
    return AuthResponse(access_token=create_access_token(user), user=UserPublic.model_validate(user))


@router.post("/refresh", response_model=AuthResponse)
def refresh_access_token(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
    db: Session = Depends(get_db),
) -> AuthResponse:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing refresh token",
    )
    if refresh_token is None:
        raise unauthorized
    try:
        claims = decode_token(refresh_token, "refresh")
    except InvalidTokenError:
        raise unauthorized from None

    user = UserRepository(db).get_by_id(claims.sub)
    if user is None or not user.is_active or user.role != claims.role:
        raise unauthorized
    if user.auth_version != claims.auth_version:
        raise unauthorized

    _set_refresh_cookie(response, create_refresh_token(user))
    return AuthResponse(access_token=create_access_token(user), user=UserPublic.model_validate(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=f"{settings.api_prefix}/auth",
        secure=settings.environment == "production",
        httponly=True,
        samesite=settings.cookie_samesite,
    )


_RESET_RESPONSE = MessageResponse(message="If an active CareLoop account exists for that email, we’ve sent password-reset instructions.")


@router.post("/forgot-password", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
def forgot_password(data: ForgotPasswordRequest, db: Session = Depends(get_db)) -> MessageResponse:
    """Always return the same response: this endpoint must not become an account oracle."""
    now = datetime.now(timezone.utc)
    user = db.scalar(select(User).where(User.email == str(data.email)).with_for_update())
    if user is None or not user.is_active:
        return _RESET_RESPONSE
    recent = db.scalar(select(PasswordResetToken).where(PasswordResetToken.user_id == user.id, PasswordResetToken.requested_at >= now - timedelta(seconds=settings.password_reset_request_cooldown_seconds), PasswordResetToken.consumed_at.is_(None), PasswordResetToken.invalidated_at.is_(None)))
    if recent:
        return _RESET_RESPONSE
    db.query(PasswordResetToken).filter(PasswordResetToken.user_id == user.id, PasswordResetToken.consumed_at.is_(None), PasswordResetToken.invalidated_at.is_(None)).update({"invalidated_at": now}, synchronize_session=False)
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    db.add(PasswordResetToken(user_id=user.id, token_hash=token_hash, requested_at=now, expires_at=now + timedelta(minutes=settings.password_reset_minutes)))
    # The one-time raw token is necessarily delivery material. It stays only in this internal outbox payload, is never logged or exposed by an API, and is removed with normal outbox retention.
    enqueue(db, event_type=NotificationEventType.PASSWORD_RESET, recipient=user, idempotency_key=f"password-reset:{token_hash}", payload={"recipient_name": user.full_name, "reset_token": raw_token, "expires_minutes": settings.password_reset_minutes})
    return _RESET_RESPONSE


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)) -> MessageResponse:
    failure = HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This password-reset link is invalid or has expired")
    if data.password != data.password_confirmation:
        raise failure
    if len(data.token) < 32 or len(data.token) > 256:
        raise failure
    token_hash = hashlib.sha256(data.token.encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc)
    record = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash).with_for_update())
    expires_at = record.expires_at.replace(tzinfo=timezone.utc) if record and record.expires_at.tzinfo is None else (record.expires_at if record else now)
    if not record or record.consumed_at or record.invalidated_at or expires_at <= now:
        raise failure
    user = db.scalar(select(User).where(User.id == record.user_id).with_for_update())
    if not user or not user.is_active:
        raise failure
    user.password_hash = hash_password(data.password)
    user.auth_version += 1
    record.consumed_at = now
    db.query(PasswordResetToken).filter(PasswordResetToken.user_id == user.id, PasswordResetToken.id != record.id, PasswordResetToken.consumed_at.is_(None), PasswordResetToken.invalidated_at.is_(None)).update({"invalidated_at": now}, synchronize_session=False)
    return MessageResponse(message="Your password has been reset. You can sign in now.")


@router.get("/me", response_model=UserPublic)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.get("/role/patient", response_model=MessageResponse)
def patient_only(
    _: User = Depends(require_roles(UserRole.PATIENT)),
) -> MessageResponse:
    return MessageResponse(message="Patient access confirmed")


@router.get("/role/doctor", response_model=MessageResponse)
def doctor_only(
    _: User = Depends(require_roles(UserRole.DOCTOR)),
) -> MessageResponse:
    return MessageResponse(message="Doctor access confirmed")


@router.get("/role/admin", response_model=MessageResponse)
def admin_only(
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> MessageResponse:
    return MessageResponse(message="Admin access confirmed")
