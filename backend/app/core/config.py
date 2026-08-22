from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LOCAL_DATABASE_URL = "postgresql+psycopg://careloop:careloop@localhost:5432/careloop"
LOCAL_JWT_SECRET = "development-only-secret-change-before-production"


class Settings(BaseSettings):
    app_name: str = "CareLoop API"
    environment: Literal["development", "test", "production"] = "development"
    api_prefix: str = "/api/v1"
    database_url: str = LOCAL_DATABASE_URL
    jwt_secret: str = LOCAL_JWT_SECRET
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    access_token_minutes: int = Field(default=15, gt=0, le=60)
    refresh_token_days: int = Field(default=7, gt=0, le=30)
    slot_hold_minutes: int = Field(default=5, ge=1, le=15)
    llm_provider: Literal["openai_compatible"] = "openai_compatible"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_model: str = "openai/gpt-oss-20b"
    llm_timeout_seconds: float = Field(default=8, gt=0, le=30)
    frontend_origin: str = "http://localhost:5173"
    email_provider: Literal["log", "sendgrid"] = "log"
    email_from_address: str = "no-reply@example.com"
    sendgrid_api_key: str = ""
    notification_max_attempts: int = Field(default=5, ge=1, le=20)
    notification_base_retry_seconds: int = Field(default=60, ge=1, le=86400)
    notification_poll_seconds: int = Field(default=5, ge=1, le=300)
    notification_stale_claim_seconds: int = Field(default=300, ge=1, le=3600)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CARELOOP_",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.environment == "production":
            missing: list[str] = []
            if self.database_url == LOCAL_DATABASE_URL:
                missing.append("CARELOOP_DATABASE_URL")
            if self.jwt_secret == LOCAL_JWT_SECRET or len(self.jwt_secret) < 32:
                missing.append("CARELOOP_JWT_SECRET (at least 32 characters)")
            if missing:
                raise ValueError(
                    "Production configuration is unsafe or missing: " + ", ".join(missing)
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
