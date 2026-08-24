from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from typing import Literal
from uuid import UUID

import jwt
from pydantic import BaseModel, ValidationError
from pwdlib import PasswordHash

from app.core.config import settings
from app.models.user import User, UserRole

password_hasher = PasswordHash.recommended()


class TokenClaims(BaseModel):
    sub: UUID
    role: UserRole
    token_type: Literal["access", "refresh"]
    exp: datetime
    iat: datetime
    auth_version: int = 0


class InvalidTokenError(Exception):
    """Raised when a token is invalid, expired, or of the wrong type."""


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return password_hasher.verify(password, password_hash)


def generate_hold_token() -> str:
    return secrets.token_urlsafe(32)


def hash_hold_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _create_token(user: User, token_type: Literal["access", "refresh"]) -> str:
    now = datetime.now(timezone.utc)
    lifetime = (
        timedelta(minutes=settings.access_token_minutes)
        if token_type == "access"
        else timedelta(days=settings.refresh_token_days)
    )
    payload = {
        "sub": str(user.id),
        "role": user.role.value,
        "token_type": token_type,
        "iat": now,
        "exp": now + lifetime,
        "auth_version": user.auth_version,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user: User) -> str:
    return _create_token(user, "access")


def create_refresh_token(user: User) -> str:
    return _create_token(user, "refresh")


def decode_token(token: str, expected_type: Literal["access", "refresh"]) -> TokenClaims:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "role", "token_type", "iat", "exp"]},
        )
        claims = TokenClaims.model_validate(payload)
    except (jwt.PyJWTError, ValidationError, ValueError, TypeError) as exc:
        raise InvalidTokenError from exc

    if claims.token_type != expected_type:
        raise InvalidTokenError
    return claims
