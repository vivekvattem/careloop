import os
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.cli.seed_demo_data import DEMO_DOCTORS
from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.db.session import SessionLocal
from app.models.user import UserRole
from app.repositories.user import UserRepository

KNOWN_DEMO_DOCTOR_EMAILS = tuple(str(doctor["email"]) for doctor in DEMO_DOCTORS)


@dataclass(frozen=True)
class ResetResult:
    updated: int
    skipped: int


def reset_demo_doctor_passwords(db: Session, password: str) -> ResetResult:
    updated = 0
    skipped = 0
    users = UserRepository(db)

    for email in KNOWN_DEMO_DOCTOR_EMAILS:
        user = users.get_by_email(email)
        if user is None or user.role != UserRole.DOCTOR:
            skipped += 1
            continue
        if verify_password(password, user.password_hash):
            skipped += 1
            continue
        users.update_password_hash(user, hash_password(password))
        updated += 1

    db.commit()
    return ResetResult(updated=updated, skipped=skipped)


def main() -> None:
    explicit_environment = os.getenv("ENVIRONMENT", "").strip().lower()
    if explicit_environment == "production" or settings.environment == "production":
        raise SystemExit("Demo doctor password reset is disabled in production.")

    password = os.getenv("DEMO_DOCTOR_PASSWORD")
    if not password:
        raise SystemExit("Set DEMO_DOCTOR_PASSWORD before running the reset command.")

    with SessionLocal() as db:
        result = reset_demo_doctor_passwords(db, password)
    print(f"Demo password reset complete: updated={result.updated}, skipped={result.skipped}")


if __name__ == "__main__":
    main()

