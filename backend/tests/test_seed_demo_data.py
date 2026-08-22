from datetime import date

import pytest
from sqlalchemy import func, select

from app.cli import seed_demo_data as seed_module
from app.core.security import verify_password
from app.models.doctor import DoctorLeave, DoctorProfile, DoctorWorkingHour
from app.models.user import User, UserRole
from tests.conftest import TestingSessionLocal

DEMO_PASSWORD = "DemoDoctors123"


def configure_seed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(seed_module, "SessionLocal", TestingSessionLocal)
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DEMO_DOCTOR_PASSWORD", DEMO_PASSWORD)


def test_first_execution_creates_complete_demo_doctors(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_seed(monkeypatch)

    seed_module.main()

    output = capsys.readouterr().out
    assert "created=6, skipped=0" in output
    assert DEMO_PASSWORD not in output
    with TestingSessionLocal() as db:
        users = list(db.scalars(select(User).where(User.role == UserRole.DOCTOR)).all())
        profiles = list(db.scalars(select(DoctorProfile)).all())
        working_hour_count = db.scalar(select(func.count()).select_from(DoctorWorkingHour))
        leaves = list(db.scalars(select(DoctorLeave)).all())

    assert len(users) == 6
    assert len(profiles) == 6
    assert {profile.specialisation for profile in profiles} == {
        "Cardiology",
        "Dermatology",
        "General Medicine",
        "Paediatrics",
        "Neurology",
        "Orthopaedics",
    }
    assert all(user.role == UserRole.DOCTOR for user in users)
    assert all(user.password_hash != DEMO_PASSWORD for user in users)
    assert all(verify_password(DEMO_PASSWORD, user.password_hash) for user in users)
    assert all(profile.timezone == "Asia/Kolkata" for profile in profiles)
    assert all(profile.slot_duration_minutes in {20, 30} for profile in profiles)
    assert working_hour_count == 72
    assert len(leaves) == 6
    assert all(leave.leave_date > date.today() for leave in leaves)


def test_repeated_execution_skips_every_existing_email(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_seed(monkeypatch)
    seed_module.main()
    capsys.readouterr()

    seed_module.main()

    output = capsys.readouterr().out
    assert "created=0, skipped=6" in output
    with TestingSessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(DoctorProfile)) == 6
        assert db.scalar(select(func.count()).select_from(DoctorWorkingHour)) == 72
        assert db.scalar(select(func.count()).select_from(DoctorLeave)) == 6


def test_production_environment_refuses_before_database_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ForbiddenSession:
        def __call__(self):
            raise AssertionError("The database must not be opened in production")

    monkeypatch.setattr(seed_module, "SessionLocal", ForbiddenSession())
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEMO_DOCTOR_PASSWORD", DEMO_PASSWORD)

    with pytest.raises(SystemExit, match="disabled in production"):
        seed_module.main()

