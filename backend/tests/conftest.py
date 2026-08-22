import os
from collections.abc import Generator
from pathlib import Path

os.environ["CARELOOP_ENVIRONMENT"] = "test"
os.environ["CARELOOP_DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["CARELOOP_JWT_SECRET"] = "test-secret-that-is-long-enough-for-tests"
os.environ["CARELOOP_LLM_API_KEY"] = ""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

_original_working_directory = Path.cwd()
os.chdir(Path(__file__).resolve().parent)
try:
    from app.core.config import Settings, get_settings
    from app.db.base import Base
    from app.db.session import get_db
    from app.main import app
    from app.services import visit as visit_service
    from app.services.llm import LLMGenerationError
finally:
    os.chdir(_original_working_directory)

_original_env_file = Settings.model_config.get("env_file")
Settings.model_config["env_file"] = None
get_settings.cache_clear()

test_engine = create_engine(
    "sqlite+pysqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
Base.metadata.create_all(bind=test_engine)


def override_get_db() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="session", autouse=True)
def restore_settings_configuration() -> Generator[None, None, None]:
    try:
        yield
    finally:
        get_settings.cache_clear()
        Settings.model_config["env_file"] = _original_env_file


class MissingConfigurationProvider:
    def generate_structured(self, *, system_prompt, user_prompt, response_schema):
        raise LLMGenerationError(
            "missing_configuration",
            "LLM API key is not configured",
            0,
        )


@pytest.fixture(autouse=True)
def isolate_test_settings(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.setenv("CARELOOP_LLM_API_KEY", "")
    monkeypatch.setattr(
        visit_service,
        "configured_provider",
        MissingConfigurationProvider,
    )
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()


@pytest.fixture(autouse=True)
def clean_database() -> Generator[None, None, None]:
    for table in reversed(Base.metadata.sorted_tables):
        with test_engine.begin() as connection:
            connection.execute(table.delete())
    yield


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def patient_payload() -> dict[str, str]:
    return {
        "full_name": "Alex Patient",
        "email": "alex@example.com",
        "password": "StrongPass123",
    }
