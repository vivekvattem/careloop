from datetime import datetime, timezone
from hashlib import sha256
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.core.config import settings
from app.models.calendar import GoogleCalendarConnection, GoogleOAuthState
from app.models.user import User, UserRole
from app.services.calendar import connect_url, consume_state, decrypt, finish_callback
from tests.conftest import TestingSessionLocal


@pytest.fixture(autouse=True)
def calendar_oauth_settings(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "test-client-id")
    monkeypatch.setattr(settings, "google_client_secret", "test-client-secret")
    monkeypatch.setattr(settings, "google_token_encryption_key", Fernet.generate_key().decode())


def patient(db):
    user = User(full_name="Calendar Patient", email=f"calendar-{uuid4()}@example.test", password_hash="not-a-password", role=UserRole.PATIENT)
    db.add(user)
    db.flush()
    return user


def test_connect_state_is_hashed_expiring_and_single_use():
    with TestingSessionLocal() as db:
        user = patient(db)
        authorization_url = connect_url(db, user.id)
        raw_state = parse_qs(urlparse(authorization_url).query)["state"][0]
        stored = db.scalar(select(GoogleOAuthState).where(GoogleOAuthState.user_id == user.id))
        assert stored.state_hash == sha256(raw_state.encode()).hexdigest()
        assert raw_state not in stored.state_hash
        assert stored.expires_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc)
        assert consume_state(db, raw_state).id == stored.id
        with pytest.raises(RuntimeError, match="Invalid or expired OAuth state"):
            consume_state(db, raw_state)


def test_callback_exchange_encrypts_tokens_and_returns_allowlisted_destination():
    class FakeProvider:
        def exchange_code(self, code):
            assert code == "authorization-code"
            return {"access_token": "access-token", "refresh_token": "refresh-token", "expires_in": 3600, "scope": "calendar.events"}

    with TestingSessionLocal() as db:
        user = patient(db)
        raw_state = parse_qs(urlparse(connect_url(db, user.id)).query)["state"][0]
        assert finish_callback(db, raw_state, "authorization-code", provider=FakeProvider()) == "/patient"
        connection = db.scalar(select(GoogleCalendarConnection).where(GoogleCalendarConnection.user_id == user.id))
        assert decrypt(connection.access_token_encrypted) == "access-token"
        assert decrypt(connection.refresh_token_encrypted) == "refresh-token"
        assert connection.access_token_encrypted != "access-token"
        assert connection.refresh_token_encrypted != "refresh-token"
