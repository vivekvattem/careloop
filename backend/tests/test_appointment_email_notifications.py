from datetime import timedelta
from uuid import UUID

from sqlalchemy import select
from fastapi.testclient import TestClient

from app.models.notification import NotificationEventType, NotificationOutbox
from app.models.user import UserRole
from app.services.notifications import _subject, _template, enqueue
from tests.conftest import TestingSessionLocal
from tests.test_appointments import book_appointment, create_hold, prepare_slot
from tests.test_doctors import auth, create_user


def event_for(db, appointment_id: str, event_type: NotificationEventType) -> NotificationOutbox:
    return db.scalar(select(NotificationOutbox).where(
        NotificationOutbox.appointment_id == UUID(appointment_id),
        NotificationOutbox.event_type == event_type,
    ))


def test_confirmation_email_snapshots_safe_details_and_localizes_time(client: TestClient):
    _, token = create_user(UserRole.PATIENT, "email-confirmation@example.test")
    doctor_id, _, start = prepare_slot(email="ananya.mehta@example.test")
    appointment_id = book_appointment(client, token, doctor_id, start).json()["id"]
    with TestingSessionLocal() as db:
        job = event_for(db, appointment_id, NotificationEventType.APPOINTMENT_CONFIRMED)
        assert set(job.payload) == {"message", "patient_name", "doctor_name", "doctor_specialisation", "slot_start", "slot_end", "timezone", "consultation_mode"}
        assert not {"symptoms", "diagnosis", "clinical_note", "private_doctor_notes", "prescriptions"} & set(job.payload)
        text = _template(job)
        assert "Hello, Test" in text
        assert "Doctor: Dr. Doctor Ananya.Mehta" in text
        assert "Specialisation: Cardiology" in text
        assert "Date: 2 March 2099" in text
        assert "Time: 9:00 AM – 9:30 AM" in text
        assert "Timezone: Asia/Kolkata" in text
        assert _subject(job) == "CareLoop appointment confirmed — Dr. Doctor Ananya.Mehta"


def test_cancellation_email_contains_appointment_details(client: TestClient):
    _, token = create_user(UserRole.PATIENT, "email-cancel@example.test")
    doctor_id, _, start = prepare_slot(email="cancel.doctor@example.test")
    appointment_id = book_appointment(client, token, doctor_id, start).json()["id"]
    response = client.post(f"/api/v1/appointments/{appointment_id}/cancel", json={"reason": "Patient request"}, headers=auth(token))
    assert response.status_code == 200
    with TestingSessionLocal() as db:
        job = event_for(db, appointment_id, NotificationEventType.APPOINTMENT_CANCELLED)
        text = _template(job)
        assert "has been cancelled" in text and "Doctor: Dr. Doctor Cancel.Doctor" in text
        assert "Time: 9:00 AM – 9:30 AM" in text


def test_reschedule_email_identifies_the_replacement_time(client: TestClient):
    _, token = create_user(UserRole.PATIENT, "email-reschedule@example.test")
    doctor_id, _, start = prepare_slot(email="reschedule.doctor@example.test")
    original_id = book_appointment(client, token, doctor_id, start).json()["id"]
    held = create_hold(client, token, doctor_id, start + timedelta(minutes=30))
    response = client.post(f"/api/v1/appointments/{original_id}/reschedule", json={"new_hold_token": held.json()["hold_token"]}, headers=auth(token))
    assert response.status_code == 200
    with TestingSessionLocal() as db:
        job = event_for(db, response.json()["id"], NotificationEventType.APPOINTMENT_RESCHEDULED)
        text = _template(job)
        assert "has been rescheduled" in text and "new appointment details" in text
        assert "Time: 9:30 AM – 10:00 AM" in text


def test_legacy_appointment_payload_falls_back_safely_and_timezone_conversion_is_correct():
    with TestingSessionLocal() as db:
        patient, _ = create_user(UserRole.PATIENT, "email-template@example.test")
        legacy = enqueue(db, event_type=NotificationEventType.APPOINTMENT_CONFIRMED, recipient=patient, idempotency_key="legacy-email", payload={"message": "Legacy appointment update"})
        converted = enqueue(db, event_type=NotificationEventType.APPOINTMENT_CONFIRMED, recipient=patient, idempotency_key="timezone-email", payload={
            "message": "ignored", "patient_name": "Aryan Kumar", "doctor_name": "Ananya Mehta", "doctor_specialisation": "Neurology",
            "slot_start": "2026-08-24T05:00:00+00:00", "slot_end": "2026-08-24T05:30:00+00:00", "timezone": "Asia/Kolkata", "consultation_mode": "video",
        })
        assert _template(legacy) == "Legacy appointment update"
        text = _template(converted)
        assert "Hello, Aryan" in text and "Date: 24 August 2026" in text
        assert "Time: 10:30 AM – 11:00 AM" in text and "Consultation mode: Online" in text
