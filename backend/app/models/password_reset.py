import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class PasswordResetToken(TimestampMixin, Base):
    """Only a SHA-256 digest is persisted; the raw delivery token never reaches this model."""

    __tablename__ = "password_reset_tokens"
    __table_args__ = (
        CheckConstraint("expires_at > requested_at", name="expires_after_request"),
        Index("ix_password_reset_tokens_user_active", "user_id", "consumed_at", "invalidated_at"),
        Index("ix_password_reset_tokens_expiry", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
