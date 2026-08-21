import os

from sqlalchemy.exc import IntegrityError

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.user import UserRole
from app.repositories.user import UserRepository
from app.schemas.user import UserCreate


def main() -> None:
    email = os.getenv("CARELOOP_ADMIN_EMAIL", "")
    password = os.getenv("CARELOOP_ADMIN_PASSWORD", "")
    full_name = os.getenv("CARELOOP_ADMIN_FULL_NAME", "Development Admin")
    if not email or not password:
        raise SystemExit(
            "Set CARELOOP_ADMIN_EMAIL and CARELOOP_ADMIN_PASSWORD before running this command."
        )

    validated = UserCreate(full_name=full_name, email=email, password=password)
    with SessionLocal() as db:
        users = UserRepository(db)
        if users.get_by_email(str(validated.email)):
            raise SystemExit("A user with that email already exists; no changes were made.")
        try:
            user = users.create(
                full_name=validated.full_name,
                email=str(validated.email),
                password_hash=hash_password(validated.password),
                role=UserRole.ADMIN,
            )
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise SystemExit("Could not create admin because the email already exists.") from exc
    print(f"Created admin account for {user.email}")


if __name__ == "__main__":
    main()

