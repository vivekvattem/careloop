"""enforce required Google Calendar relationship columns"""

from alembic import op
import sqlalchemy as sa


revision = "20260822_08"
down_revision = "20260822_07"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("google_calendar_connections", "user_id", existing_type=sa.Uuid(), nullable=False)
    op.alter_column("google_oauth_states", "state_hash", existing_type=sa.String(64), nullable=False)
    op.alter_column("google_oauth_states", "user_id", existing_type=sa.Uuid(), nullable=False)
    op.alter_column("calendar_sync_jobs", "appointment_id", existing_type=sa.Uuid(), nullable=False)
    op.alter_column("calendar_sync_jobs", "user_id", existing_type=sa.Uuid(), nullable=False)
    op.alter_column("calendar_sync_jobs", "idempotency_key", existing_type=sa.String(255), nullable=False)


def downgrade():
    op.alter_column("calendar_sync_jobs", "idempotency_key", existing_type=sa.String(255), nullable=True)
    op.alter_column("calendar_sync_jobs", "user_id", existing_type=sa.Uuid(), nullable=True)
    op.alter_column("calendar_sync_jobs", "appointment_id", existing_type=sa.Uuid(), nullable=True)
    op.alter_column("google_oauth_states", "user_id", existing_type=sa.Uuid(), nullable=True)
    op.alter_column("google_oauth_states", "state_hash", existing_type=sa.String(64), nullable=True)
    op.alter_column("google_calendar_connections", "user_id", existing_type=sa.Uuid(), nullable=True)
