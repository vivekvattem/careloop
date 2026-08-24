import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from app.core.config import Settings


def production_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "production",
        "database_url": "postgresql+psycopg://user:password@db.example.invalid/careloop",
        "jwt_secret": "x" * 32,
        "frontend_origin": "https://app.example.invalid",
        "cors_origins": "https://app.example.invalid",
        "public_api_url": "https://api.example.invalid",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.mark.parametrize(
    "database_url",
    ["", "sqlite+pysqlite:///careloop.db", "postgresql+psycopg://careloop:careloop@localhost:5432/careloop"],
)
def test_production_rejects_missing_or_local_database(database_url: str) -> None:
    with pytest.raises(ValidationError, match="CARELOOP_DATABASE_URL"):
        production_settings(database_url=database_url)


def test_production_requires_strong_jwt_and_explicit_credentialed_cors() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        production_settings(jwt_secret="development-only-secret-change-before-production")
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        production_settings(cors_origins="*")
    with pytest.raises(ValidationError, match="must include"):
        production_settings(cors_origins="https://other.example.invalid")


def test_optional_integrations_are_not_required_when_disabled() -> None:
    settings = production_settings()
    assert settings.llm_enabled is False
    assert settings.google_calendar_enabled is False


def test_enabled_integrations_require_safe_credentials_and_urls() -> None:
    with pytest.raises(ValidationError, match="LLM_API_KEY"):
        production_settings(llm_enabled=True)
    with pytest.raises(ValidationError, match="GOOGLE_TOKEN_ENCRYPTION_KEY"):
        production_settings(google_calendar_enabled=True)
    settings = production_settings(
        google_calendar_enabled=True,
        google_token_encryption_key=Fernet.generate_key().decode(),
        google_client_id="calendar-client-id",
        google_client_secret="calendar-client-secret",
        google_redirect_uri="https://api.example.invalid/api/v1/integrations/google-calendar/callback",
    )
    assert settings.google_calendar_enabled is True


def test_delivery_policy_rejects_log_or_missing_selected_provider_key() -> None:
    with pytest.raises(ValidationError, match="EMAIL_PROVIDER"):
        production_settings(email_delivery_required=True)
    with pytest.raises(ValidationError, match="RESEND_API_KEY"):
        production_settings(email_delivery_required=True, email_provider="resend")
    assert production_settings(email_delivery_required=True, email_provider="resend", resend_api_key="configured-key").email_provider == "resend"


def test_cross_site_cookie_requires_https_public_api_url() -> None:
    with pytest.raises(ValidationError, match="PUBLIC_API_URL"):
        production_settings(cookie_samesite="none", public_api_url="http://api.example.invalid")
