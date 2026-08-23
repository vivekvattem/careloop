from datetime import datetime, timezone
from uuid import uuid4

import httpx
import pytest
from cryptography.fernet import Fernet

from app.core.config import settings
from app.models.calendar import CalendarConnectionStatus, GoogleCalendarConnection
from app.services.calendar import GoogleProvider, GoogleProviderError, decrypt, encrypt
from tests.conftest import TestingSessionLocal


@pytest.fixture(autouse=True)
def temporary_key(monkeypatch):
    monkeypatch.setattr(settings, "google_token_encryption_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "google_client_id", "client-id")
    monkeypatch.setattr(settings, "google_client_secret", "client-secret")


def connection(refresh="refresh-token"):
    return GoogleCalendarConnection(user_id=uuid4(), access_token_encrypted=encrypt("old-access"), refresh_token_encrypted=encrypt(refresh) if refresh else None, token_expiry=datetime(2020, 1, 1, tzinfo=timezone.utc), scopes="calendar.events", calendar_id="primary", status=CalendarConnectionStatus.CONNECTED)


def transport(response, seen=None):
    def handler(request):
        if seen is not None: seen.append(request)
        return response(request) if callable(response) else response
    return httpx.MockTransport(handler)


def test_refresh_persists_new_access_token_expiry_and_preserves_refresh_token():
    seen=[]; provider=GoogleProvider(transport=transport(httpx.Response(200, json={"access_token":"new-access","expires_in":3600,"scope":"calendar.events"}), seen))
    with TestingSessionLocal() as db:
        item=connection(); db.add(item); db.commit(); provider.refresh(db,item); db.refresh(item)
        assert decrypt(item.access_token_encrypted)=="new-access"; assert decrypt(item.refresh_token_encrypted)=="refresh-token"; assert item.token_expiry.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc); assert seen[0].url.path == "/token"


def test_refresh_rotated_token_is_encrypted_and_persisted():
    provider=GoogleProvider(transport=transport(httpx.Response(200,json={"access_token":"new","refresh_token":"rotated","expires_in":10})))
    with TestingSessionLocal() as db:
        item=connection(); db.add(item); db.commit(); provider.refresh(db,item); assert decrypt(item.refresh_token_encrypted)=="rotated"; assert item.refresh_token_encrypted != "rotated"


@pytest.mark.parametrize("response,category,retryable", [(httpx.Response(400,text='{"error":"invalid_grant"}'),"reauthorization_required",False),(httpx.Response(401),"reauthorization_required",False),(httpx.Response(403),"reauthorization_required",False),(httpx.Response(429),"provider_unavailable",True),(httpx.Response(500),"provider_unavailable",True),(httpx.Response(400),"provider_rejected",False)])
def test_refresh_error_classification(response, category, retryable):
    provider=GoogleProvider(transport=transport(response))
    with TestingSessionLocal() as db:
        item=connection(); db.add(item); db.commit()
        with pytest.raises(GoogleProviderError) as raised: provider.refresh(db,item)
        assert raised.value.category==category and raised.value.retryable is retryable


def test_timeout_and_connection_are_retryable():
    def fail(_): raise httpx.ReadTimeout("timed out")
    provider=GoogleProvider(transport=transport(fail))
    with pytest.raises(GoogleProviderError) as raised: provider.create_event(connection(), event_payload())
    assert raised.value.category=="connection" and raised.value.retryable


def event_payload():
    return {"summary":"CareLoop appointment","start":"2026-08-24T09:00:00+05:30","end":"2026-08-24T09:30:00+05:30","timezone":"Asia/Kolkata","consultation_mode":"video","careloop_appointment_reference":"appointment-123"}


def test_create_update_payload_is_minimal_and_delete_is_idempotent():
    requests=[]; provider=GoogleProvider(transport=transport(httpx.Response(200,json={"id":"event-1"}),requests)); item=connection()
    assert provider.create_event(item,event_payload())["event_id"]=="event-1"; assert provider.update_event(item,"event-1",event_payload())["event_id"]=="event-1"
    assert {"summary","start","end","timezone","consultation_mode","careloop_appointment_reference"} == set(event_payload())
    with pytest.raises(GoogleProviderError): provider.create_event(item,event_payload()|{"symptoms":"private"})
    assert provider.delete_event(item,None)=={"deleted":True}
    for status in (404,410): assert GoogleProvider(transport=transport(httpx.Response(status))).delete_event(item,"missing")=={"deleted":True}


def test_provider_safe_errors_do_not_include_tokens_or_codes():
    provider=GoogleProvider(transport=transport(httpx.Response(401,text="secret-token")))
    with pytest.raises(GoogleProviderError) as raised: provider.refresh(TestingSessionLocal(),connection("secret-refresh"))
    assert "secret" not in str(raised.value).lower()
