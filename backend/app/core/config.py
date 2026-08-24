from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LOCAL_DATABASE_URL = "postgresql+psycopg://careloop:careloop@localhost:5432/careloop"
LOCAL_JWT_SECRET = "development-only-secret-change-before-production"


def normalize_database_url(database_url: str) -> str:
    """Select the project's Psycopg 3 dialect for Render and legacy URLs.

    Render supplies PostgreSQL URLs with a bare ``postgresql://`` scheme.
    SQLAlchemy associates that scheme with psycopg2 by default, which CareLoop
    intentionally does not install. Replacing only the leading scheme preserves
    the complete credential, host, database, query, and SSL portion verbatim.
    """
    if database_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + database_url.removeprefix("postgresql://")
    if database_url.startswith("postgres://"):
        return "postgresql+psycopg://" + database_url.removeprefix("postgres://")
    return database_url


class Settings(BaseSettings):
    app_name: str = "CareLoop API"
    environment: Literal["development", "test", "production"] = "development"
    api_prefix: str = "/api/v1"
    database_url: str = LOCAL_DATABASE_URL
    jwt_secret: str = LOCAL_JWT_SECRET
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    access_token_minutes: int = Field(default=15, gt=0, le=60)
    refresh_token_days: int = Field(default=7, gt=0, le=30)
    password_reset_minutes: int = Field(default=20, ge=5, le=60)
    password_reset_request_cooldown_seconds: int = Field(default=60, ge=10, le=3600)
    slot_hold_minutes: int = Field(default=5, ge=1, le=15)
    llm_provider: Literal["openai_compatible"] = "openai_compatible"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_model: str = "openai/gpt-oss-20b"
    llm_timeout_seconds: float = Field(default=8, gt=0, le=30)
    llm_enabled: bool = False
    frontend_origin: str = "http://localhost:5173"
    cors_origins: str = ""
    public_api_url: str = ""
    cookie_samesite: Literal["lax", "none", "strict"] = "lax"
    email_provider: Literal["log", "sendgrid", "resend", "smtp"] = "log"
    email_from_address: str = "notifications@careloop.app"
    sendgrid_api_key: str = ""
    resend_api_key: str = ""
    resend_base_url: str = "https://api.resend.com"
    email_timeout_seconds: float = Field(default=8, gt=0, le=30)
    smtp_host: str = "localhost"
    smtp_port: int = Field(default=1025, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_starttls: bool = False
    notification_max_attempts: int = Field(default=5, ge=1, le=20)
    notification_base_retry_seconds: int = Field(default=60, ge=1, le=86400)
    notification_poll_seconds: int = Field(default=5, ge=1, le=300)
    notification_stale_claim_seconds: int = Field(default=300, ge=1, le=3600)
    email_delivery_required: bool = False
    google_calendar_enabled: bool = False
    google_client_id: str = ""; google_client_secret: str = ""; google_redirect_uri: str = "http://localhost:8000/api/v1/integrations/google-calendar/callback"; google_token_encryption_key: str = ""; google_calendar_scopes: str = "https://www.googleapis.com/auth/calendar.events"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CARELOOP_",
        extra="ignore",
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_connection_url(cls, value: object) -> object:
        return normalize_database_url(value) if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if bool(self.smtp_username) != bool(self.smtp_password):
            raise ValueError("CARELOOP_SMTP_USERNAME and CARELOOP_SMTP_PASSWORD must be supplied together")
        if self.environment == "production":
            missing: list[str] = []
            if not self.database_url or self.database_url == LOCAL_DATABASE_URL or self.database_url.startswith("sqlite"):
                missing.append("CARELOOP_DATABASE_URL")
            if self.jwt_secret == LOCAL_JWT_SECRET or len(self.jwt_secret) < 32 or _placeholder(self.jwt_secret):
                missing.append("CARELOOP_JWT_SECRET (at least 32 characters)")
            if not _secure_url(self.frontend_origin):
                missing.append("CARELOOP_FRONTEND_ORIGIN (HTTPS production URL)")
            if self.cors_origin_list == ["*"] or "*" in self.cors_origin_list:
                missing.append("CARELOOP_CORS_ORIGINS (explicit origins required)")
            if self.frontend_origin not in self.cors_origin_list:
                missing.append("CARELOOP_CORS_ORIGINS (must include CARELOOP_FRONTEND_ORIGIN)")
            if self.cookie_samesite == "none" and not _secure_url(self.public_api_url):
                missing.append("CARELOOP_PUBLIC_API_URL (HTTPS required for SameSite=None cookies)")
            if self.llm_enabled and (not self.llm_api_key or _placeholder(self.llm_api_key)):
                missing.append("CARELOOP_LLM_API_KEY")
            if self.google_calendar_enabled:
                if not self.google_token_encryption_key or _placeholder(self.google_token_encryption_key):
                    missing.append("CARELOOP_GOOGLE_TOKEN_ENCRYPTION_KEY")
                if not self.google_client_id or not self.google_client_secret or _placeholder(self.google_client_id) or _placeholder(self.google_client_secret):
                    missing.append("CARELOOP_GOOGLE_CLIENT_ID/CARELOOP_GOOGLE_CLIENT_SECRET")
                if not _secure_url(self.google_redirect_uri) or not _secure_url(self.public_api_url):
                    missing.append("CARELOOP_GOOGLE_REDIRECT_URI/CARELOOP_PUBLIC_API_URL")
            if self.email_delivery_required and self.email_provider == "log":
                missing.append("CARELOOP_EMAIL_PROVIDER (real delivery provider required)")
            if self.email_delivery_required and self.email_provider == "sendgrid" and (
                not self.sendgrid_api_key or _placeholder(self.sendgrid_api_key)
            ):
                missing.append("CARELOOP_SENDGRID_API_KEY")
            if self.email_delivery_required and self.email_provider == "resend" and (
                not self.resend_api_key or _placeholder(self.resend_api_key)
            ):
                missing.append("CARELOOP_RESEND_API_KEY")
            if missing:
                raise ValueError(
                    "Production configuration is unsafe or missing: " + ", ".join(missing)
                )
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [value.strip() for value in (self.cors_origins or self.frontend_origin).split(",") if value.strip()]


def _placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return not normalized or normalized.startswith(("your_", "replace", "example", "placeholder"))


def _secure_url(value: str) -> bool:
    parsed = urlparse(value)
    hostname = parsed.hostname or ""
    return parsed.scheme == "https" and bool(parsed.netloc) and "localhost" not in hostname.lower()


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
