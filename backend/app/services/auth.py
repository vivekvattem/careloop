from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models.user import User, UserRole
from app.repositories.user import UserRepository
from app.schemas.user import UserCreate


class DuplicateEmailError(Exception):
    """Raised when an email already belongs to a user."""


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)

    def register_patient(self, data: UserCreate) -> User:
        if self.users.get_by_email(str(data.email)):
            raise DuplicateEmailError
        try:
            return self.users.create(
                full_name=data.full_name,
                email=str(data.email),
                password_hash=hash_password(data.password),
                role=UserRole.PATIENT,
            )
        except IntegrityError as exc:
            self.db.rollback()
            raise DuplicateEmailError from exc

    def authenticate(self, email: str, password: str) -> User | None:
        user = self.users.get_by_email(email)
        if user is None or not verify_password(password, user.password_hash):
            return None
        if not user.is_active:
            return None
        return user

