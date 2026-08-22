from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models.appointment import (
    Appointment,
    AppointmentStatus,
    AppointmentStatusHistory,
    HoldStatus,
    SlotHold,
)
from app.models.doctor import DoctorLeave
from app.models.user import UserRole
from app.schemas.appointment import SymptomInput
from app.services.appointment import AppointmentService, HoldConflictError
from tests.conftest import TestingSessionLocal
from tests.test_doctors import add_interval, auth, create_doctor, create_user

FUTURE_DATE = date(2099, 3, 2)
ZONE = ZoneInfo("Asia/Kolkata")


def symptoms() -> dict[str, object]:
    return {
        "chief_complaint": "Persistent headache",
        "symptom_description": "A fictional headache used for appointment testing.",
        "duration": "Three days",
        "severity": 6,
        "existing_conditions": "None",
        "current_medications": None,
    }


def prepare_slot(
    *, email: str = "book.doctor@example.com", active: bool = True
) -> tuple[object, str, datetime]:
    doctor_id, _, doctor_token = create_doctor(email, is_active=active)
    add_interval(doctor_id, FUTURE_DATE, time(9), time(11))
    return doctor_id, doctor_token, datetime.combine(FUTURE_DATE, time(9), ZONE)


def create_hold(client: TestClient, token: str, doctor_id, slot_start: datetime):
    return client.post(
        "/api/v1/appointments/holds",
        json={"doctor_id": str(doctor_id), "slot_start": slot_start.isoformat()},
        headers=auth(token),
    )


def confirm(client: TestClient, token: str, hold_token: str, symptom_data=None):
    return client.post(
        "/api/v1/appointments",
        json={"hold_token": hold_token, "symptoms": symptom_data or symptoms()},
        headers=auth(token),
    )


def book_appointment(client: TestClient, patient_token: str, doctor_id, start: datetime):
    held = create_hold(client, patient_token, doctor_id, start)
    assert held.status_code == 201
    booked = confirm(client, patient_token, held.json()["hold_token"])
    assert booked.status_code == 201
    return booked


@pytest.mark.parametrize(
    "start_time",
    [time(8), time(9, 10)],
    ids=["outside_working_hours", "misaligned"],
)
def test_invalid_schedule_hold_is_rejected(client: TestClient, start_time: time) -> None:
    _, patient_token = create_user(UserRole.PATIENT, "patient@example.com")
    doctor_id, _, _ = prepare_slot()

    response = create_hold(
        client,
        patient_token,
        doctor_id,
        datetime.combine(FUTURE_DATE, start_time, ZONE),
    )

    assert response.status_code == 422


def test_past_inactive_and_leave_slots_are_rejected(client: TestClient) -> None:
    _, patient_token = create_user(UserRole.PATIENT, "patient@example.com")
    past_id, _, _ = create_doctor("past@example.com")
    past_date = date(2020, 1, 6)
    add_interval(past_id, past_date, time(9), time(10))
    inactive_id, _, inactive_start = prepare_slot(email="inactive@example.com", active=False)
    leave_id, _, leave_start = prepare_slot(email="leave@example.com")
    with TestingSessionLocal() as db:
        db.add(
            DoctorLeave(
                doctor_profile_id=leave_id,
                leave_date=FUTURE_DATE,
                reason="Test leave",
            )
        )
        db.commit()

    past = create_hold(
        client, patient_token, past_id, datetime.combine(past_date, time(9), ZONE)
    )
    inactive = create_hold(client, patient_token, inactive_id, inactive_start)
    leave = create_hold(client, patient_token, leave_id, leave_start)

    assert past.status_code == 422
    assert inactive.status_code == 404
    assert leave.status_code == 422


def test_hold_token_is_hashed_and_cross_patient_use_is_rejected(client: TestClient) -> None:
    patient_one, token_one = create_user(UserRole.PATIENT, "one@example.com")
    _, token_two = create_user(UserRole.PATIENT, "two@example.com")
    doctor_id, _, start = prepare_slot()
    held = create_hold(client, token_one, doctor_id, start)
    raw_token = held.json()["hold_token"]

    with TestingSessionLocal() as db:
        stored = db.scalar(select(SlotHold))
    assert stored is not None
    assert stored.patient_user_id == patient_one.id
    assert stored.token_hash != raw_token
    assert raw_token not in stored.token_hash
    assert confirm(client, token_two, raw_token).status_code == 403


def test_expired_hold_can_be_replaced() -> None:
    patient, _ = create_user(UserRole.PATIENT, "patient@example.com")
    doctor_id, _, start = prepare_slot()
    first_now = datetime(2099, 3, 1, 10, tzinfo=timezone.utc)
    with TestingSessionLocal() as db:
        first = AppointmentService(db).create_hold(patient, doctor_id, start, now=first_now)
    with TestingSessionLocal() as db:
        second = AppointmentService(db).create_hold(
            patient, doctor_id, start, now=first_now + timedelta(minutes=6)
        )
    assert first.hold_token != second.hold_token
    with TestingSessionLocal() as db:
        statuses = list(db.scalars(select(SlotHold.status).order_by(SlotHold.created_at)))
    assert statuses == [HoldStatus.EXPIRED, HoldStatus.ACTIVE]


def test_expired_hold_cannot_be_confirmed() -> None:
    patient, _ = create_user(UserRole.PATIENT, "patient@example.com")
    doctor_id, _, start = prepare_slot()
    first_now = datetime(2099, 3, 1, 10, tzinfo=timezone.utc)
    with TestingSessionLocal() as db:
        held = AppointmentService(db).create_hold(patient, doctor_id, start, now=first_now)
    with TestingSessionLocal() as db:
        with pytest.raises(HoldConflictError):
            AppointmentService(db).confirm(
                patient,
                held.hold_token,
                SymptomInput(**symptoms()),
                now=first_now + timedelta(minutes=6),
            )
    with TestingSessionLocal() as db:
        assert db.get(SlotHold, held.hold_id).status == HoldStatus.EXPIRED


def test_consumed_and_released_holds_cannot_be_used(client: TestClient) -> None:
    patient, patient_token = create_user(UserRole.PATIENT, "patient@example.com")
    doctor_id, _, start = prepare_slot()
    held = create_hold(client, patient_token, doctor_id, start)
    raw_token = held.json()["hold_token"]
    assert confirm(client, patient_token, raw_token).status_code == 201
    assert confirm(client, patient_token, raw_token).status_code == 409

    second_start = start + timedelta(minutes=30)
    with TestingSessionLocal() as db:
        released = AppointmentService(db).create_hold(patient, doctor_id, second_start)
        stored = db.scalar(select(SlotHold).where(SlotHold.id == released.hold_id))
        stored.status = HoldStatus.RELEASED
        db.commit()
    assert confirm(client, patient_token, released.hold_token).status_code == 409


@pytest.mark.parametrize(
    "change",
    [
        {"severity": 11},
        {"symptom_description": ""},
    ],
    ids=["severity", "missing_description"],
)
def test_symptom_validation(client: TestClient, change: dict[str, object]) -> None:
    _, patient_token = create_user(UserRole.PATIENT, "patient@example.com")
    doctor_id, _, start = prepare_slot()
    held = create_hold(client, patient_token, doctor_id, start)
    data = symptoms() | change

    response = confirm(client, patient_token, held.json()["hold_token"], data)

    assert response.status_code == 422


def test_confirmation_creates_symptoms_history_and_isolated_views(client: TestClient) -> None:
    patient, patient_token = create_user(UserRole.PATIENT, "patient@example.com")
    _, other_patient_token = create_user(UserRole.PATIENT, "other@example.com")
    doctor_id, doctor_token, start = prepare_slot()
    _, _, other_doctor_token = create_doctor("other.doctor@example.com")
    booked = book_appointment(client, patient_token, doctor_id, start)
    appointment_id = UUID(booked.json()["id"])

    patient_list = client.get("/api/v1/appointments/me", headers=auth(patient_token))
    other_patient = client.get(
        f"/api/v1/appointments/{appointment_id}", headers=auth(other_patient_token)
    )
    doctor_detail = client.get(
        f"/api/v1/doctor/me/appointments/{appointment_id}", headers=auth(doctor_token)
    )
    other_doctor = client.get(
        f"/api/v1/doctor/me/appointments/{appointment_id}",
        headers=auth(other_doctor_token),
    )

    assert patient_list.status_code == 200
    assert "symptom_description" not in patient_list.text
    assert other_patient.status_code == 404
    assert doctor_detail.status_code == 200
    assert doctor_detail.json()["symptoms"]["severity"] == 6
    assert other_doctor.status_code == 404
    assert booked.json()["history"][0]["new_status"] == "confirmed"
    assert booked.json()["patient_user_id"] == str(patient.id)


def test_cancellation_releases_slot_and_invalid_transition_is_rejected(
    client: TestClient,
) -> None:
    _, patient_token = create_user(UserRole.PATIENT, "patient@example.com")
    doctor_id, _, start = prepare_slot()
    booked = book_appointment(client, patient_token, doctor_id, start)
    appointment_id = UUID(booked.json()["id"])

    cancelled = client.post(
        f"/api/v1/appointments/{appointment_id}/cancel",
        json={"reason": "Plans changed"},
        headers=auth(patient_token),
    )
    repeated = client.post(
        f"/api/v1/appointments/{appointment_id}/cancel",
        json={"reason": "Again"},
        headers=auth(patient_token),
    )
    replacement_hold = create_hold(client, patient_token, doctor_id, start)

    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert repeated.status_code == 409
    assert replacement_hold.status_code == 201


def test_slot_preview_excludes_hold_and_appointment_then_restores_cancelled_slot(
    client: TestClient,
) -> None:
    _, patient_token = create_user(UserRole.PATIENT, "patient@example.com")
    doctor_id, _, start = prepare_slot()
    preview_url = f"/api/v1/doctors/{doctor_id}/slots?date={FUTURE_DATE}"

    initial = client.get(preview_url, headers=auth(patient_token))
    held = create_hold(client, patient_token, doctor_id, start)
    during_hold = client.get(preview_url, headers=auth(patient_token))
    booked = confirm(client, patient_token, held.json()["hold_token"])
    during_booking = client.get(preview_url, headers=auth(patient_token))
    cancelled = client.post(
        f"/api/v1/appointments/{booked.json()['id']}/cancel",
        json={"reason": "Plans changed"},
        headers=auth(patient_token),
    )
    after_cancel = client.get(preview_url, headers=auth(patient_token))

    def starts(response) -> set[str]:
        assert response.status_code == 200
        return {slot["start"] for slot in response.json()["slots"]}

    expected = start.isoformat()
    assert expected in starts(initial)
    assert expected not in starts(during_hold)
    assert expected not in starts(during_booking)
    assert cancelled.status_code == 200
    assert expected in starts(after_cancel)


def test_failed_reschedule_preserves_original(client: TestClient) -> None:
    _, patient_token = create_user(UserRole.PATIENT, "patient@example.com")
    doctor_id, _, start = prepare_slot()
    booked = book_appointment(client, patient_token, doctor_id, start)
    appointment_id = UUID(booked.json()["id"])

    response = client.post(
        f"/api/v1/appointments/{appointment_id}/reschedule",
        json={"new_hold_token": "not-a-real-hold-token-value", "reason": "Move"},
        headers=auth(patient_token),
    )

    assert response.status_code == 409
    with TestingSessionLocal() as db:
        original = db.get(Appointment, appointment_id)
    assert original.status == AppointmentStatus.CONFIRMED


def test_successful_reschedule_creates_linked_replacement_and_preserves_symptoms(
    client: TestClient,
) -> None:
    _, patient_token = create_user(UserRole.PATIENT, "patient@example.com")
    doctor_id, _, start = prepare_slot()
    original_response = book_appointment(client, patient_token, doctor_id, start)
    original_id = UUID(original_response.json()["id"])
    new_hold = create_hold(client, patient_token, doctor_id, start + timedelta(minutes=30))

    response = client.post(
        f"/api/v1/appointments/{original_id}/reschedule",
        json={"new_hold_token": new_hold.json()["hold_token"], "reason": "New time"},
        headers=auth(patient_token),
    )

    assert response.status_code == 200
    assert response.json()["rescheduled_from_id"] == str(original_id)
    assert response.json()["symptoms"]["chief_complaint"] == "Persistent headache"
    with TestingSessionLocal() as db:
        original = db.get(Appointment, original_id)
        replacement = db.get(Appointment, UUID(response.json()["id"]))
    assert original.status == AppointmentStatus.CANCELLED
    assert replacement.status == AppointmentStatus.CONFIRMED


def test_leave_conflict_preview_and_confirmed_application(client: TestClient) -> None:
    _, patient_token = create_user(UserRole.PATIENT, "patient@example.com")
    _, second_patient_token = create_user(UserRole.PATIENT, "patient.two@example.com")
    _, admin_token = create_user(UserRole.ADMIN, "admin@example.com")
    doctor_id, _, start = prepare_slot()
    booked = book_appointment(client, patient_token, doctor_id, start)
    second = book_appointment(
        client, second_patient_token, doctor_id, start + timedelta(minutes=30)
    )
    appointment_ids = [UUID(booked.json()["id"]), UUID(second.json()["id"])]
    leave_url = f"/api/v1/admin/doctors/{doctor_id}/leave"

    preview = client.get(
        f"/api/v1/admin/doctors/{doctor_id}/leave-conflicts?date={FUTURE_DATE}",
        headers=auth(admin_token),
    )
    refused = client.post(
        leave_url,
        json={"leave_date": str(FUTURE_DATE), "reason": "Conference"},
        headers=auth(admin_token),
    )
    with TestingSessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(DoctorLeave)) == 0
        assert all(
            db.get(Appointment, appointment_id).status == AppointmentStatus.CONFIRMED
            for appointment_id in appointment_ids
        )
    applied = client.post(
        f"{leave_url}?confirm_conflicts=true",
        json={"leave_date": str(FUTURE_DATE), "reason": "Conference"},
        headers=auth(admin_token),
    )

    assert preview.status_code == 200
    assert preview.json()["affected_count"] == 2
    assert refused.status_code == 409
    assert refused.json()["detail"]["code"] == "leave_conflicts"
    assert applied.status_code == 201
    assert applied.json()["affected_count"] == 2
    with TestingSessionLocal() as db:
        appointments = [db.get(Appointment, item) for item in appointment_ids]
        history_count = db.scalar(
            select(func.count())
            .select_from(AppointmentStatusHistory)
            .where(AppointmentStatusHistory.appointment_id.in_(appointment_ids))
        )
    assert all(
        appointment.status == AppointmentStatus.RESCHEDULE_REQUIRED
        for appointment in appointments
    )
    assert history_count == 4
