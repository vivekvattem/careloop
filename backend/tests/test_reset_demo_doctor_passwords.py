import pytest
from sqlalchemy import select

from app.cli import reset_demo_doctor_passwords as reset_module
from app.cli.seed_demo_data import DEMO_DOCTORS, seed_demo_data
from app.core.security import hash_password, verify_password
from app.models.user import User, UserRole
from tests.conftest import TestingSessionLocal

OLD_PASSWORD = "OldDemoDoctors123"
NEW_PASSWORD = "NewDemoDoctors456"


class ForbiddenSession:
    def __call__(self):
        raise AssertionError("The database must not be opened")


def seed_known_doctors() -> None:
    with TestingSessionLocal() as db:
        result = seed_demo_data(db, OLD_PASSWORD)
    assert result.created == 6


def test_successful_reset_updates_all_known_demo_doctors(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    seed_known_doctors()
    monkeypatch.setattr(reset_module, "SessionLocal", TestingSessionLocal)
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DEMO_DOCTOR_PASSWORD", NEW_PASSWORD)

    reset_module.main()

    output = capsys.readouterr().out
    assert output.strip() == "Demo password reset complete: updated=6, skipped=0"
    assert NEW_PASSWORD not in output
    with TestingSessionLocal() as db:
        users = [
            db.scalar(select(User).where(User.email == str(doctor["email"])))
            for doctor in DEMO_DOCTORS
        ]
    assert all(user is not None for user in users)
    assert all(verify_password(NEW_PASSWORD, user.password_hash) for user in users if user)
    assert all(not verify_password(OLD_PASSWORD, user.password_hash) for user in users if user)


def test_missing_password_refuses_before_database_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(reset_module, "SessionLocal", ForbiddenSession())
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.delenv("DEMO_DOCTOR_PASSWORD", raising=False)

    with pytest.raises(SystemExit, match="Set DEMO_DOCTOR_PASSWORD"):
        reset_module.main()


def test_production_refuses_before_database_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(reset_module, "SessionLocal", ForbiddenSession())
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEMO_DOCTOR_PASSWORD", NEW_PASSWORD)

    with pytest.raises(SystemExit, match="disabled in production"):
        reset_module.main()


def test_reset_excludes_accounts_outside_the_six_email_allowlist(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    seed_known_doctors()
    protected_emails = ["outsider@demo.careloop", "regular.doctor@example.com"]
    with TestingSessionLocal() as db:
        for email in protected_emails:
            db.add(
                User(
                    full_name="Non-demo Doctor",
                    email=email,
                    password_hash=hash_password(OLD_PASSWORD),
                    role=UserRole.DOCTOR,
                )
            )
        db.commit()

    monkeypatch.setattr(reset_module, "SessionLocal", TestingSessionLocal)
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DEMO_DOCTOR_PASSWORD", NEW_PASSWORD)
    reset_module.main()
    capsys.readouterr()

    with TestingSessionLocal() as db:
        protected_users = [
            db.scalar(select(User).where(User.email == email)) for email in protected_emails
        ]
    assert all(user is not None for user in protected_users)
    assert all(verify_password(OLD_PASSWORD, user.password_hash) for user in protected_users if user)
    assert all(
        not verify_password(NEW_PASSWORD, user.password_hash)
        for user in protected_users
        if user
    )

