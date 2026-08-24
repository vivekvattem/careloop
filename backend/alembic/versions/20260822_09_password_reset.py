"""add password reset tokens and authentication version"""

from alembic import op
import sqlalchemy as sa


revision = "20260822_09"
down_revision = "20260822_08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("auth_version", sa.Integer(), nullable=False, server_default="0"))
    op.alter_column("users", "auth_version", server_default=None)
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("invalidated_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("expires_at > requested_at", name="expires_after_request"),
        sa.UniqueConstraint("token_hash", name=op.f("uq_password_reset_tokens_token_hash")),
    )
    op.create_index("ix_password_reset_tokens_user_active", "password_reset_tokens", ["user_id", "consumed_at", "invalidated_at"])
    op.create_index("ix_password_reset_tokens_expiry", "password_reset_tokens", ["expires_at"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TYPE notification_event_type ADD VALUE IF NOT EXISTS 'password_reset'")


def downgrade() -> None:
    op.drop_index("ix_password_reset_tokens_expiry", table_name="password_reset_tokens")
    op.drop_index("ix_password_reset_tokens_user_active", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
    op.drop_column("users", "auth_version")
