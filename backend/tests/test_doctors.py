from datetime import date, datetime, time
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.security import create_access_token, hash_password, verify_password
from app.models.doctor import DoctorProfile, DoctorWorkingHour
from app.models.user import User, UserRole
from app.repositories.doctor import DoctorRepository
from app.schemas.doctor import DoctorProvisionRequest
from app.services.doctor import DoctorManagementService, DoctorProvisioningError, SlotGenerationService
from tests.conftest import TestingSessionLocal


def create_user(role: UserRole, email: str) -> tuple[User, str]:
    with TestingSessionLocal() as db:
        user = User(
            full_name=f"Test {role.value.title()}",
            email=email,
            password_hash=hash_password("StrongPass123"),
            role=role,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        token = create_access_token(user)
        db.expunge(user)
    return user, token


def create_doctor(
    email: str = "doctor@example.com",
    *,
    specialisation: str = "Cardiology",
    is_active: bool = True,
    is_available: bool = True,
    slot_duration: int = 30,
) -> tuple[UUID, User, str]:
    with TestingSessionLocal() as db:
        user = User(
            full_name=f"Doctor {email.split('@')[0].title()}",
            email=email,
            password_hash=hash_password("StrongPass123"),
            role=UserRole.DOCTOR,
            is_active=is_active,
        )
        profile = DoctorProfile(
            user=user,
            specialisation=specialisation,
            qualifications="MBBS, MD",
            biography="Experienced clinician",
            consultation_mode="hybrid",
            location="Central Clinic",
            slot_duration_minutes=slot_duration,
            timezone="Asia/Kolkata",
            is_available_for_booking=is_available,
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
        token = create_access_token(user)
        doctor_id = profile.id
        db.expunge(user)
    return doctor_id, user, token


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def provisioning_payload(email: str = "new.doctor@example.com") -> dict[str, object]:
    return {
        "full_name": "Dr New Doctor",
        "email": email,
        "initial_password": "StrongPass123",
        "specialisation": "Neurology",
        "qualifications": "MBBS, DM",
        "biography": "Neurology specialist",
        "consultation_mode": "in_person",
        "location": "CareLoop Clinic",
        "slot_duration_minutes": 30,
        "timezone": "Asia/Kolkata",
        "is_available_for_booking": True,
    }


def test_unauthenticated_admin_request_is_rejected(client: TestClient) -> None:
    assert client.get("/api/v1/admin/doctors").status_code == 401


def test_patient_is_rejected_from_admin_routes(client: TestClient) -> None:
    _, token = create_user(UserRole.PATIENT, "patient@example.com")

    assert client.get("/api/v1/admin/doctors", headers=auth(token)).status_code == 403


def test_doctor_is_rejected_from_admin_routes(client: TestClient) -> None:
    _, _, token = create_doctor()

    assert client.get("/api/v1/admin/doctors", headers=auth(token)).status_code == 403


def test_admin_provisions_doctor_and_profile_atomically(client: TestClient) -> None:
    _, admin_token = create_user(UserRole.ADMIN, "admin@example.com")

    response = client.post(
        "/api/v1/admin/doctors",
        json=provisioning_payload(),
        headers=auth(admin_token),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["role"] == "doctor"
    assert body["specialisation"] == "Neurology"
    assert "initial_password" not in response.text
    assert "password_hash" not in response.text
    with TestingSessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "new.doctor@example.com"))
        profile = db.scalar(select(DoctorProfile).where(DoctorProfile.user_id == user.id))
    assert user is not None
    assert profile is not None
    assert user.role == UserRole.DOCTOR
    assert user.password_hash != "StrongPass123"
    assert verify_password("StrongPass123", user.password_hash)


def test_duplicate_doctor_email_is_rejected(client: TestClient) -> None:
    _, admin_token = create_user(UserRole.ADMIN, "admin@example.com")
    create_user(UserRole.PATIENT, "taken@example.com")

    response = client.post(
        "/api/v1/admin/doctors",
        json=provisioning_payload("TAKEN@example.com"),
        headers=auth(admin_token),
    )

    assert response.status_code == 409


def test_invalid_specialisation_is_rejected(client: TestClient) -> None:
    _, admin_token = create_user(UserRole.ADMIN, "admin@example.com")
    payload = provisioning_payload()
    payload["specialisation"] = "   "

    response = client.post("/api/v1/admin/doctors", json=payload, headers=auth(admin_token))

    assert response.status_code == 422


def test_provisioning_rolls_back_user_when_profile_creation_fails(monkeypatch) -> None:
    data = DoctorProvisionRequest.model_validate(provisioning_payload("rollback@example.com"))

    def fail_profile(*args, **kwargs):
        raise IntegrityError("profile insert", {}, Exception("forced failure"))

    monkeypatch.setattr(DoctorRepository, "create_profile", fail_profile)
    with TestingSessionLocal() as db:
        with pytest.raises(DoctorProvisioningError):
            DoctorManagementService(db).provision(data)
        assert db.scalar(select(User).where(User.email == "rollback@example.com")) is None


def test_valid_and_non_overlapping_working_hours_are_accepted(client: TestClient) -> None:
    _, admin_token = create_user(UserRole.ADMIN, "admin@example.com")
    doctor_id, _, _ = create_doctor()

    first = client.post(
        f"/api/v1/admin/doctors/{doctor_id}/working-hours",
        json={"day_of_week": 0, "start_time": "09:00", "end_time": "12:00"},
        headers=auth(admin_token),
    )
    second = client.post(
        f"/api/v1/admin/doctors/{doctor_id}/working-hours",
        json={"day_of_week": 0, "start_time": "12:00", "end_time": "15:00"},
        headers=auth(admin_token),
    )

    assert first.status_code == 201
    assert second.status_code == 201


def test_start_after_end_is_rejected(client: TestClient) -> None:
    _, admin_token = create_user(UserRole.ADMIN, "admin@example.com")
    doctor_id, _, _ = create_doctor()

    response = client.post(
        f"/api/v1/admin/doctors/{doctor_id}/working-hours",
        json={"day_of_week": 1, "start_time": "12:00", "end_time": "09:00"},
        headers=auth(admin_token),
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "start,end",
    [("09:00", "12:00"), ("10:00", "13:00")],
    ids=["duplicate", "overlap"],
)
def test_duplicate_or_overlapping_working_hour_is_rejected(
    client: TestClient, start: str, end: str
) -> None:
    _, admin_token = create_user(UserRole.ADMIN, "admin@example.com")
    doctor_id, _, _ = create_doctor()
    endpoint = f"/api/v1/admin/doctors/{doctor_id}/working-hours"
    client.post(
        endpoint,
        json={"day_of_week": 2, "start_time": "09:00", "end_time": "12:00"},
        headers=auth(admin_token),
    )

    response = client.post(
        endpoint,
        json={"day_of_week": 2, "start_time": start, "end_time": end},
        headers=auth(admin_token),
    )

    assert response.status_code == 409


def test_leave_creation_duplicate_rejection_and_removal(client: TestClient) -> None:
    _, admin_token = create_user(UserRole.ADMIN, "admin@example.com")
    doctor_id, _, _ = create_doctor()
    endpoint = f"/api/v1/admin/doctors/{doctor_id}/leave"
    payload = {"leave_date": "2099-02-03", "reason": "Private medical reason"}

    created = client.post(endpoint, json=payload, headers=auth(admin_token))
    duplicate = client.post(endpoint, json=payload, headers=auth(admin_token))
    deleted = client.delete(
        f"{endpoint}/{created.json()['id']}", headers=auth(admin_token)
    )

    assert created.status_code == 201
    assert duplicate.status_code == 409
    assert deleted.status_code == 204


def test_patient_discovery_does_not_expose_leave_reason(client: TestClient) -> None:
    _, patient_token = create_user(UserRole.PATIENT, "patient@example.com")
    doctor_id, _, _ = create_doctor()
    with TestingSessionLocal() as db:
        profile = DoctorRepository(db).get_by_id(doctor_id)
        DoctorRepository(db).add_leave(
            profile=profile,
            leave_date=date(2099, 2, 3),
            reason="Private medical reason",
        )
        db.commit()

    response = client.get(f"/api/v1/doctors/{doctor_id}", headers=auth(patient_token))

    assert response.status_code == 200
    assert "Private medical reason" not in response.text
    assert "leaves" not in response.json()


def test_patient_search_is_case_insensitive_partial_paginated_and_excludes_inactive(
    client: TestClient,
) -> None:
    _, patient_token = create_user(UserRole.PATIENT, "patient@example.com")
    create_doctor("heart1@example.com", specialisation="Cardiology")
    create_doctor("heart2@example.com", specialisation="Paediatric Cardiology")
    create_doctor("inactive@example.com", specialisation="Cardiology", is_active=False)
    create_doctor("neuro@example.com", specialisation="Neurology")

    first = client.get(
        "/api/v1/doctors?specialisation=CARDIO&page=1&page_size=1",
        headers=auth(patient_token),
    )
    second = client.get(
        "/api/v1/doctors?specialisation=cardio&page=2&page_size=1",
        headers=auth(patient_token),
    )

    assert first.status_code == 200
    assert first.json()["total"] == 2
    assert len(first.json()["items"]) == 1
    assert len(second.json()["items"]) == 1
    assert first.json()["items"][0]["id"] != second.json()["items"][0]["id"]


def test_doctor_can_retrieve_only_own_profile(client: TestClient) -> None:
    own_id, _, doctor_token = create_doctor("one@example.com")
    other_id, _, _ = create_doctor("two@example.com")

    own = client.get("/api/v1/doctor/me/profile", headers=auth(doctor_token))
    other_admin_route = client.get(
        f"/api/v1/admin/doctors/{other_id}", headers=auth(doctor_token)
    )

    assert own.status_code == 200
    assert own.json()["id"] == str(own_id)
    assert own.json()["id"] != str(other_id)
    assert other_admin_route.status_code == 403


def add_interval(doctor_id: UUID, requested_date: date, start: time, end: time) -> None:
    with TestingSessionLocal() as db:
        db.add(
            DoctorWorkingHour(
                doctor_profile_id=doctor_id,
                day_of_week=requested_date.weekday(),
                start_time=start,
                end_time=end,
            )
        )
        db.commit()


def test_slot_generation_excludes_partial_slot_and_returns_timezone_aware_values() -> None:
    doctor_id, _, _ = create_doctor(slot_duration=30)
    requested_date = date(2099, 1, 5)
    add_interval(doctor_id, requested_date, time(9), time(10, 15))

    with TestingSessionLocal() as db:
        preview = SlotGenerationService(db).generate(
            doctor_id,
            requested_date,
            now=datetime(2099, 1, 4, tzinfo=ZoneInfo("Asia/Kolkata")),
        )

    assert [(slot.start.time(), slot.end.time()) for slot in preview.slots] == [
        (time(9), time(9, 30)),
        (time(9, 30), time(10)),
    ]
    assert all(slot.start.utcoffset() is not None for slot in preview.slots)
    assert preview.timezone == "Asia/Kolkata"


def test_leave_and_inactive_doctor_return_no_slots() -> None:
    requested_date = date(2099, 1, 5)
    leave_doctor_id, _, _ = create_doctor("leave@example.com")
    inactive_doctor_id, _, _ = create_doctor("off@example.com", is_available=False)
    add_interval(leave_doctor_id, requested_date, time(9), time(11))
    with TestingSessionLocal() as db:
        profile = DoctorRepository(db).get_by_id(leave_doctor_id)
        DoctorRepository(db).add_leave(
            profile=profile, leave_date=requested_date, reason="Unavailable"
        )
        db.commit()
    with TestingSessionLocal() as db:
        service = SlotGenerationService(db)
        on_leave = service.generate(leave_doctor_id, requested_date)
        inactive = service.generate(inactive_doctor_id, requested_date)

    assert on_leave.availability == "on_leave"
    assert on_leave.slots == []
    assert inactive.availability == "doctor_inactive"
    assert inactive.slots == []


def test_past_slots_are_excluded() -> None:
    doctor_id, _, _ = create_doctor(slot_duration=30)
    requested_date = date(2099, 1, 5)
    add_interval(doctor_id, requested_date, time(9), time(11))

    with TestingSessionLocal() as db:
        preview = SlotGenerationService(db).generate(
            doctor_id,
            requested_date,
            now=datetime(2099, 1, 5, 9, 45, tzinfo=ZoneInfo("Asia/Kolkata")),
        )

    assert [slot.start.time() for slot in preview.slots] == [time(10), time(10, 30)]

