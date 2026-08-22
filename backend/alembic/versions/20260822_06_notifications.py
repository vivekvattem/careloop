"""durable notification outbox and medication reminder schedules

Revision ID: 20260822_06
Revises: 20260822_05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260822_06"
down_revision = "20260822_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    event = postgresql.ENUM("appointment_confirmed", "appointment_cancelled", "appointment_rescheduled", "post_visit_approved", "medication_reminder_due", name="notification_event_type", create_type=False)
    status = postgresql.ENUM("pending", "processing", "sent", "retry_scheduled", "permanently_failed", "cancelled", name="notification_status", create_type=False)
    event.create(op.get_bind(), checkfirst=True); status.create(op.get_bind(), checkfirst=True)
    op.create_table("notification_outbox", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("event_type", event, nullable=False), sa.Column("recipient_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False), sa.Column("recipient_email", sa.String(320), nullable=False), sa.Column("appointment_id", sa.Uuid(), sa.ForeignKey("appointments.id", ondelete="CASCADE")), sa.Column("prescription_item_id", sa.Uuid(), sa.ForeignKey("prescription_items.id", ondelete="CASCADE")), sa.Column("idempotency_key", sa.String(255), nullable=False, unique=True), sa.Column("payload", sa.JSON(), nullable=False), sa.Column("status", status, nullable=False), sa.Column("attempt_count", sa.Integer(), nullable=False), sa.Column("maximum_attempts", sa.Integer(), nullable=False), sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False), sa.Column("claimed_at", sa.DateTime(timezone=True)), sa.Column("claimed_by", sa.String(120)), sa.Column("provider", sa.String(80), nullable=False), sa.Column("provider_message_id", sa.String(255)), sa.Column("failure_category", sa.String(80)), sa.Column("failure_message", sa.String(255)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("sent_at", sa.DateTime(timezone=True)))
    op.create_index("ix_notification_outbox_due", "notification_outbox", ["status", "next_attempt_at"])
    op.create_table("medication_reminder_schedules", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("prescription_item_id", sa.Uuid(), sa.ForeignKey("prescription_items.id", ondelete="CASCADE"), nullable=False), sa.Column("patient_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False), sa.Column("reminder_time", sa.Time(), nullable=False), sa.Column("timezone", sa.String(64), nullable=False), sa.Column("next_due_at", sa.DateTime(timezone=True)), sa.Column("is_active", sa.Boolean(), nullable=False), sa.Column("cancelled_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.UniqueConstraint("prescription_item_id", "reminder_time", name="uq_medication_reminder_item_time"))
    op.create_index("ix_medication_reminder_due", "medication_reminder_schedules", ["is_active", "next_due_at"])


def downgrade() -> None:
    op.drop_index("ix_medication_reminder_due", table_name="medication_reminder_schedules"); op.drop_table("medication_reminder_schedules")
    op.drop_index("ix_notification_outbox_due", table_name="notification_outbox"); op.drop_table("notification_outbox")
    sa.Enum(name="notification_status").drop(op.get_bind(), checkfirst=True); sa.Enum(name="notification_event_type").drop(op.get_bind(), checkfirst=True)
