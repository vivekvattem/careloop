from datetime import datetime, timedelta, timezone
import hashlib
import pytest
from sqlalchemy.exc import IntegrityError

from app.core.security import create_access_token, create_refresh_token
from app.models.notification import NotificationEventType, NotificationOutbox
from app.models.password_reset import PasswordResetToken
from app.models.user import User
from tests.conftest import TestingSessionLocal


@pytest.fixture
def db_session():
    with TestingSessionLocal() as db:
        yield db


def _register(client, email="reset@example.com", password="StrongPass123"):
    assert client.post("/api/v1/auth/register", json={"full_name": "Reset Patient", "email": email, "password": password}).status_code == 201


def test_forgot_password_is_non_enumerating_and_stores_only_hash(client, db_session):
    _register(client)
    known = client.post("/api/v1/auth/forgot-password", json={"email": "RESET@example.com"})
    unknown = client.post("/api/v1/auth/forgot-password", json={"email": "missing@example.com"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    job = db_session.query(NotificationOutbox).one()
    assert job.event_type == NotificationEventType.PASSWORD_RESET
    raw = job.payload["reset_token"]
    record = db_session.query(PasswordResetToken).one()
    assert record.token_hash == hashlib.sha256(raw.encode()).hexdigest()
    assert raw not in known.text


def test_reset_is_single_use_and_invalidates_existing_tokens(client, db_session):
    _register(client)
    client.post("/api/v1/auth/forgot-password", json={"email": "reset@example.com"})
    raw = db_session.query(NotificationOutbox).one().payload["reset_token"]
    response = client.post("/api/v1/auth/reset-password", json={"token": raw, "password": "NewStrongPass123", "password_confirmation": "NewStrongPass123"})
    assert response.status_code == 200
    assert client.post("/api/v1/auth/reset-password", json={"token": raw, "password": "AnotherPass123", "password_confirmation": "AnotherPass123"}).status_code == 400
    assert client.post("/api/v1/auth/login", json={"email": "reset@example.com", "password": "StrongPass123"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "reset@example.com", "password": "NewStrongPass123"}).status_code == 200


def test_expired_and_malformed_reset_tokens_fail_safely(client, db_session):
    _register(client)
    user = db_session.query(User).filter_by(email="reset@example.com").one()
    raw = "x" * 43
    db_session.add(PasswordResetToken(user_id=user.id, token_hash=hashlib.sha256(raw.encode()).hexdigest(), requested_at=datetime.now(timezone.utc) - timedelta(minutes=30), expires_at=datetime.now(timezone.utc) - timedelta(minutes=10)))
    db_session.commit()
    for token in (raw, "bad"):
        response = client.post("/api/v1/auth/reset-password", json={"token": token, "password": "NewStrongPass123", "password_confirmation": "NewStrongPass123"})
        assert response.status_code == 400
        assert "invalid" in response.text.lower() or "expired" in response.text.lower()


def test_password_reset_invalidates_access_and_refresh_tokens(client, db_session):
    _register(client)
    user = db_session.query(User).filter_by(email="reset@example.com").one()
    access, refresh = create_access_token(user), create_refresh_token(user)
    client.post("/api/v1/auth/forgot-password", json={"email": user.email})
    raw = db_session.query(NotificationOutbox).one().payload["reset_token"]
    assert client.post("/api/v1/auth/reset-password", json={"token": raw, "password": "NewStrongPass123", "password_confirmation": "NewStrongPass123"}).status_code == 200
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"}).status_code == 401
    assert client.post("/api/v1/auth/refresh", cookies={"careloop_refresh": refresh}).status_code == 401


def test_inactive_user_receives_same_response_without_job(client, db_session):
    _register(client)
    db_session.query(User).filter_by(email="reset@example.com").one().is_active = False
    db_session.commit()
    response = client.post("/api/v1/auth/forgot-password", json={"email": "reset@example.com"})
    assert response.status_code == 202
    assert db_session.query(NotificationOutbox).count() == 0


def test_token_hash_is_unique_and_lookup_is_supported(db_session, client):
    _register(client)
    user = db_session.query(User).filter_by(email="reset@example.com").one()
    now = datetime.now(timezone.utc)
    token_hash = hashlib.sha256(b"unique-token-hash-test").hexdigest()
    db_session.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash,
            requested_at=now,
            expires_at=now + timedelta(minutes=20),
        )
    )
    db_session.commit()
    assert db_session.query(PasswordResetToken).filter_by(token_hash=token_hash).one().user_id == user.id
    db_session.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash,
            requested_at=now,
            expires_at=now + timedelta(minutes=20),
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
