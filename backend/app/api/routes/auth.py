from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import get_current_user, require_roles
from app.core.config import settings
from app.core.security import (
    InvalidTokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.db.session import get_db
from app.models.user import User, UserRole
from app.repositories.user import UserRepository
from app.schemas.auth import AuthResponse, LoginRequest, MessageResponse
from app.schemas.user import UserCreate, UserPublic
from app.services.auth import AuthService, DuplicateEmailError

router = APIRouter(prefix="/auth", tags=["authentication"])
REFRESH_COOKIE_NAME = "careloop_refresh"


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
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

    _set_refresh_cookie(response, create_refresh_token(user))
    return AuthResponse(access_token=create_access_token(user), user=UserPublic.model_validate(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=f"{settings.api_prefix}/auth",
        secure=settings.environment == "production",
        httponly=True,
        samesite="lax",
    )


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

