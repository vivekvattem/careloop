from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User, UserRole


class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, user_id: UUID) -> User | None:
        return self.db.scalar(select(User).where(User.id == user_id))

    def get_by_email(self, email: str) -> User | None:
        return self.db.scalar(select(User).where(User.email == email.lower()))

    def create(
        self,
        *,
        full_name: str,
        email: str,
        password_hash: str,
        role: UserRole = UserRole.PATIENT,
    ) -> User:
        user = User(
            full_name=full_name,
            email=email.lower(),
            password_hash=password_hash,
            role=role,
        )
        self.db.add(user)
        self.db.flush()
        self.db.refresh(user)
        return user

    def update_password_hash(self, user: User, password_hash: str) -> None:
        user.password_hash = password_hash
        self.db.flush()

