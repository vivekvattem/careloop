"""Add visit intelligence, summaries, and patient-history RAG.

Revision ID: 20260822_04
Revises: 20260822_03
Create Date: 2026-08-22
"""

from collections.abc import Sequence
import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "20260822_04"
down_revision: str | None = "20260822_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

generation_status = sa.Enum(
    "pending", "completed", "fallback", "retry_pending", "failed", name="generation_status"
)
generation_source = sa.Enum("llm", "deterministic_fallback", name="generation_source")
summary_urgency = sa.Enum("Low", "Medium", "High", name="summary_urgency")
review_status = sa.Enum("pending_review", "approved", "rejected", name="review_status")
care_document_type = sa.Enum(
    "symptoms",
    "clinical_note",
    "prescription",
    "approved_post_visit",
    name="care_document_type",
)


def _summary_metadata_columns() -> list[sa.Column]:
    return [
        sa.Column("status", generation_status, nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model_identifier", sa.String(length=160), nullable=False),
        sa.Column("prompt_version", sa.String(length=40), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("failure_category", sa.String(length=80), nullable=True),
        sa.Column("failure_message", sa.String(length=255), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("historical_context_used", sa.Boolean(), nullable=False),
        sa.Column("generation_source", generation_source, nullable=True),
    ]


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "clinical_notes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("doctor_user_id", sa.Uuid(), nullable=False),
        sa.Column("original_notes", sa.Text(), nullable=False),
        sa.Column("diagnosis", sa.Text(), nullable=True),
        sa.Column("follow_up_instructions", sa.Text(), nullable=False),
        sa.Column("recommended_follow_up_date", sa.Date(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"], ondelete="CASCADE", name=op.f("fk_clinical_notes_appointment_id_appointments")),
        sa.ForeignKeyConstraint(["doctor_user_id"], ["users.id"], ondelete="RESTRICT", name=op.f("fk_clinical_notes_doctor_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_clinical_notes")),
        sa.UniqueConstraint("appointment_id", name=op.f("uq_clinical_notes_appointment_id")),
    )
    op.create_table(
        "prescriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("clinical_note_id", sa.Uuid(), nullable=False),
        sa.Column("prescribing_doctor_user_id", sa.Uuid(), nullable=False),
        sa.Column("general_instructions", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"], ondelete="CASCADE", name=op.f("fk_prescriptions_appointment_id_appointments")),
        sa.ForeignKeyConstraint(["clinical_note_id"], ["clinical_notes.id"], ondelete="CASCADE", name=op.f("fk_prescriptions_clinical_note_id_clinical_notes")),
        sa.ForeignKeyConstraint(["prescribing_doctor_user_id"], ["users.id"], ondelete="RESTRICT", name=op.f("fk_prescriptions_prescribing_doctor_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prescriptions")),
        sa.UniqueConstraint("appointment_id", name=op.f("uq_prescriptions_appointment_id")),
        sa.UniqueConstraint("clinical_note_id", name="uq_prescriptions_clinical_note_id"),
    )
    op.create_table(
        "prescription_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("prescription_id", sa.Uuid(), nullable=False),
        sa.Column("medication_name", sa.String(length=200), nullable=False),
        sa.Column("dosage", sa.String(length=120), nullable=False),
        sa.Column("route", sa.String(length=80), nullable=True),
        sa.Column("frequency_per_day", sa.Integer(), nullable=False),
        sa.Column("reminder_times", sa.JSON(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("food_instructions", sa.String(length=255), nullable=True),
        sa.Column("additional_instructions", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("frequency_per_day BETWEEN 1 AND 24", name=op.f("ck_prescription_items_frequency_range")),
        sa.CheckConstraint("end_date IS NULL OR end_date >= start_date", name=op.f("ck_prescription_items_valid_date_range")),
        sa.ForeignKeyConstraint(["prescription_id"], ["prescriptions.id"], ondelete="CASCADE", name=op.f("fk_prescription_items_prescription_id_prescriptions")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prescription_items")),
    )
    op.create_index("ix_prescription_items_prescription", "prescription_items", ["prescription_id"])
    op.create_table(
        "pre_visit_summaries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        *_summary_metadata_columns(),
        sa.Column("urgency", summary_urgency, nullable=True),
        sa.Column("chief_complaint", sa.String(length=200), nullable=True),
        sa.Column("suggested_questions", sa.JSON(), nullable=True),
        sa.Column("relevant_history_note", sa.Text(), nullable=True),
        sa.Column("safety_disclaimer", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("attempt_count >= 0", name=op.f("ck_pre_visit_summaries_attempt_count_nonnegative")),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"], ondelete="CASCADE", name=op.f("fk_pre_visit_summaries_appointment_id_appointments")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pre_visit_summaries")),
        sa.UniqueConstraint("appointment_id", name=op.f("uq_pre_visit_summaries_appointment_id")),
    )
    op.create_table(
        "post_visit_summaries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        *_summary_metadata_columns(),
        sa.Column("patient_friendly_summary", sa.Text(), nullable=True),
        sa.Column("medication_schedule", sa.JSON(), nullable=True),
        sa.Column("follow_up_steps", sa.JSON(), nullable=True),
        sa.Column("warning_signs", sa.JSON(), nullable=True),
        sa.Column("review_status", review_status, nullable=False),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_content", sa.JSON(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("attempt_count >= 0", name=op.f("ck_post_visit_summaries_attempt_count_nonnegative")),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"], ondelete="CASCADE", name=op.f("fk_post_visit_summaries_appointment_id_appointments")),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL", name=op.f("fk_post_visit_summaries_reviewed_by_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_post_visit_summaries")),
        sa.UniqueConstraint("appointment_id", name=op.f("uq_post_visit_summaries_appointment_id")),
    )
    op.create_table(
        "care_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("patient_user_id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("document_type", care_document_type, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("event_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("doctor_verified", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"], ondelete="CASCADE", name=op.f("fk_care_documents_appointment_id_appointments")),
        sa.ForeignKeyConstraint(["patient_user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_care_documents_patient_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_care_documents")),
    )
    op.create_index("ix_care_documents_patient_event", "care_documents", ["patient_user_id", "event_date"])
    op.create_index("ix_care_documents_appointment", "care_documents", ["appointment_id"])
    op.create_table(
        "pre_visit_summary_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("pre_visit_summary_id", sa.Uuid(), nullable=False),
        sa.Column("care_document_id", sa.Uuid(), nullable=False),
        sa.Column("rank_position", sa.Integer(), nullable=False),
        sa.Column("ranking_score", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("rank_position BETWEEN 1 AND 3", name=op.f("ck_pre_visit_summary_sources_rank_position_range")),
        sa.ForeignKeyConstraint(["care_document_id"], ["care_documents.id"], ondelete="CASCADE", name=op.f("fk_pre_visit_summary_sources_care_document_id_care_documents")),
        sa.ForeignKeyConstraint(["pre_visit_summary_id"], ["pre_visit_summaries.id"], ondelete="CASCADE", name=op.f("fk_pre_visit_summary_sources_pre_visit_summary_id_pre_visit_summaries")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pre_visit_summary_sources")),
        sa.UniqueConstraint("pre_visit_summary_id", "care_document_id", name="uq_pre_visit_summary_sources_pair"),
    )

    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT a.id AS appointment_id, a.patient_user_id, a.slot_start, "
            "s.chief_complaint, s.symptom_description, s.duration, s.severity "
            "FROM appointments a JOIN symptom_submissions s ON s.appointment_id = a.id"
        )
    ).mappings()
    pre_table = sa.table(
        "pre_visit_summaries",
        sa.column("id", sa.Uuid()),
        sa.column("appointment_id", sa.Uuid()),
        sa.column("status", generation_status),
        sa.column("provider", sa.String()),
        sa.column("model_identifier", sa.String()),
        sa.column("prompt_version", sa.String()),
        sa.column("attempt_count", sa.Integer()),
        sa.column("historical_context_used", sa.Boolean()),
    )
    document_table = sa.table(
        "care_documents",
        sa.column("id", sa.Uuid()),
        sa.column("patient_user_id", sa.Uuid()),
        sa.column("appointment_id", sa.Uuid()),
        sa.column("document_type", care_document_type),
        sa.column("content", sa.Text()),
        sa.column("event_date", sa.DateTime(timezone=True)),
        sa.column("doctor_verified", sa.Boolean()),
    )
    for row in rows:
        connection.execute(
            pre_table.insert().values(
                id=uuid.uuid4(),
                appointment_id=row["appointment_id"],
                status="pending",
                provider="openai_compatible",
                model_identifier="openai/gpt-oss-20b",
                prompt_version="pre_visit_v1",
                attempt_count=0,
                historical_context_used=False,
            )
        )
        connection.execute(
            document_table.insert().values(
                id=uuid.uuid4(),
                patient_user_id=row["patient_user_id"],
                appointment_id=row["appointment_id"],
                document_type="symptoms",
                content=(
                    f"Chief complaint: {row['chief_complaint']}. "
                    f"Description: {row['symptom_description']}. Duration: {row['duration']}. "
                    f"Severity: {row['severity']}/10."
                ),
                event_date=row["slot_start"],
                doctor_verified=False,
            )
        )


def downgrade() -> None:
    op.drop_table("pre_visit_summary_sources")
    op.drop_index("ix_care_documents_appointment", table_name="care_documents")
    op.drop_index("ix_care_documents_patient_event", table_name="care_documents")
    op.drop_table("care_documents")
    op.drop_table("post_visit_summaries")
    op.drop_table("pre_visit_summaries")
    op.drop_index("ix_prescription_items_prescription", table_name="prescription_items")
    op.drop_table("prescription_items")
    op.drop_table("prescriptions")
    op.drop_table("clinical_notes")
    care_document_type.drop(op.get_bind(), checkfirst=True)
    review_status.drop(op.get_bind(), checkfirst=True)
    summary_urgency.drop(op.get_bind(), checkfirst=True)
    generation_source.drop(op.get_bind(), checkfirst=True)
    generation_status.drop(op.get_bind(), checkfirst=True)
