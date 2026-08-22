"""Add concurrency-safe appointment booking.

Revision ID: 20260822_03
Revises: 20260822_02
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260822_03"
down_revision: str | None = "20260822_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

hold_status = sa.Enum("active", "consumed", "expired", "released", name="hold_status")
appointment_status = sa.Enum(
    "confirmed",
    "completed",
    "cancelled",
    "reschedule_required",
    name="appointment_status",
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.create_table(
        "slot_holds",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("doctor_profile_id", sa.Uuid(), nullable=False),
        sa.Column("patient_user_id", sa.Uuid(), nullable=False),
        sa.Column("slot_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("slot_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("status", hold_status, server_default="active", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("slot_start < slot_end", name=op.f("ck_slot_holds_start_before_end")),
        sa.ForeignKeyConstraint(["doctor_profile_id"], ["doctor_profiles.id"], ondelete="CASCADE", name=op.f("fk_slot_holds_doctor_profile_id_doctor_profiles")),
        sa.ForeignKeyConstraint(["patient_user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_slot_holds_patient_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_slot_holds")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_slot_holds_token_hash")),
    )
    op.create_index("ix_slot_holds_doctor_time", "slot_holds", ["doctor_profile_id", "slot_start", "slot_end"])
    op.create_index("ix_slot_holds_patient_status", "slot_holds", ["patient_user_id", "status"])

    op.create_table(
        "appointments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("patient_user_id", sa.Uuid(), nullable=False),
        sa.Column("doctor_profile_id", sa.Uuid(), nullable=False),
        sa.Column("slot_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("slot_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", appointment_status, server_default="confirmed", nullable=False),
        sa.Column("cancellation_reason", sa.String(length=500), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rescheduled_from_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("slot_start < slot_end", name=op.f("ck_appointments_start_before_end")),
        sa.ForeignKeyConstraint(["doctor_profile_id"], ["doctor_profiles.id"], ondelete="RESTRICT", name=op.f("fk_appointments_doctor_profile_id_doctor_profiles")),
        sa.ForeignKeyConstraint(["patient_user_id"], ["users.id"], ondelete="RESTRICT", name=op.f("fk_appointments_patient_user_id_users")),
        sa.ForeignKeyConstraint(["rescheduled_from_id"], ["appointments.id"], ondelete="SET NULL", name=op.f("fk_appointments_rescheduled_from_id_appointments")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_appointments")),
        sa.UniqueConstraint("rescheduled_from_id", name=op.f("uq_appointments_rescheduled_from_id")),
    )
    op.create_index("ix_appointments_patient_start", "appointments", ["patient_user_id", "slot_start"])
    op.create_index("ix_appointments_doctor_start", "appointments", ["doctor_profile_id", "slot_start"])
    op.create_index("ix_appointments_status", "appointments", ["status"])

    op.create_table(
        "symptom_submissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("chief_complaint", sa.String(length=200), nullable=False),
        sa.Column("symptom_description", sa.Text(), nullable=False),
        sa.Column("duration", sa.String(length=120), nullable=False),
        sa.Column("severity", sa.Integer(), nullable=False),
        sa.Column("existing_conditions", sa.Text(), nullable=True),
        sa.Column("current_medications", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("severity BETWEEN 1 AND 10", name=op.f("ck_symptom_submissions_severity_range")),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"], ondelete="CASCADE", name=op.f("fk_symptom_submissions_appointment_id_appointments")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_symptom_submissions")),
        sa.UniqueConstraint("appointment_id", name=op.f("uq_symptom_submissions_appointment_id")),
    )

    op.create_table(
        "appointment_status_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("previous_status", appointment_status, nullable=True),
        sa.Column("new_status", appointment_status, nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL", name=op.f("fk_appointment_status_history_actor_user_id_users")),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"], ondelete="CASCADE", name=op.f("fk_appointment_status_history_appointment_id_appointments")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_appointment_status_history")),
    )
    op.create_index("ix_appointment_status_history_appointment_created", "appointment_status_history", ["appointment_id", "created_at"])

    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE slot_holds ADD CONSTRAINT ex_slot_holds_active_overlap "
            "EXCLUDE USING gist (doctor_profile_id WITH =, tstzrange(slot_start, slot_end, '[)') WITH &&) "
            "WHERE (status = 'active')"
        )
        op.execute(
            "ALTER TABLE appointments ADD CONSTRAINT ex_appointments_active_overlap "
            "EXCLUDE USING gist (doctor_profile_id WITH =, tstzrange(slot_start, slot_end, '[)') WITH &&) "
            "WHERE (status IN ('confirmed', 'reschedule_required'))"
        )


def downgrade() -> None:
    op.drop_index("ix_appointment_status_history_appointment_created", table_name="appointment_status_history")
    op.drop_table("appointment_status_history")
    op.drop_table("symptom_submissions")
    op.drop_index("ix_appointments_status", table_name="appointments")
    op.drop_index("ix_appointments_doctor_start", table_name="appointments")
    op.drop_index("ix_appointments_patient_start", table_name="appointments")
    op.drop_table("appointments")
    op.drop_index("ix_slot_holds_patient_status", table_name="slot_holds")
    op.drop_index("ix_slot_holds_doctor_time", table_name="slot_holds")
    op.drop_table("slot_holds")
    appointment_status.drop(op.get_bind(), checkfirst=True)
    hold_status.drop(op.get_bind(), checkfirst=True)
