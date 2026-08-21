import os
from collections.abc import Generator

os.environ["CARELOOP_ENVIRONMENT"] = "test"
os.environ["CARELOOP_DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["CARELOOP_JWT_SECRET"] = "test-secret-that-is-long-enough-for-tests"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app

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

