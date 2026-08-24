from sqlalchemy import create_engine

from app.core.config import Settings, normalize_database_url


def test_render_postgresql_url_uses_psycopg3_dialect_and_preserves_components() -> None:
    source = "postgresql://user%40name:pa%3Ass@db.example.invalid:5432/careloop?sslmode=require&connect_timeout=8"
    settings = Settings(_env_file=None, database_url=source)

    assert settings.database_url == "postgresql+psycopg://user%40name:pa%3Ass@db.example.invalid:5432/careloop?sslmode=require&connect_timeout=8"
    assert create_engine(settings.database_url).dialect.driver == "psycopg"


def test_legacy_postgres_url_is_normalized() -> None:
    assert normalize_database_url("postgres://user:password@db.example.invalid/careloop?sslmode=require") == (
        "postgresql+psycopg://user:password@db.example.invalid/careloop?sslmode=require"
    )


def test_explicit_psycopg_and_sqlite_urls_remain_unchanged() -> None:
    psycopg_url = "postgresql+psycopg://user:password@db.example.invalid/careloop?sslmode=require"
    sqlite_url = "sqlite+pysqlite:///:memory:"

    assert normalize_database_url(psycopg_url) == psycopg_url
    assert normalize_database_url(sqlite_url) == sqlite_url


def test_production_validation_accepts_normalized_render_url() -> None:
    settings = Settings(
        _env_file=None,
        environment="production",
        database_url="postgresql://user:password@db.example.invalid/careloop?sslmode=require",
        jwt_secret="x" * 32,
        frontend_origin="https://app.example.invalid",
        cors_origins="https://app.example.invalid",
        public_api_url="https://api.example.invalid",
    )

    assert settings.database_url.startswith("postgresql+psycopg://")


def test_application_and_alembic_share_the_settings_database_url() -> None:
    settings = Settings(_env_file=None, database_url="postgresql://user:password@db.example.invalid/careloop")

    # app.db.session and alembic/env.py both consume settings.database_url.
    assert create_engine(settings.database_url).url.drivername == "postgresql+psycopg"
    assert settings.database_url == normalize_database_url("postgresql://user:password@db.example.invalid/careloop")
