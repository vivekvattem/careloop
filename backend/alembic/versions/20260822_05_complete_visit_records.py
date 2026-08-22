"""Complete the visit-record and post-visit summary metadata.

Revision ID: 20260822_05
Revises: 20260822_04
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260822_05"
down_revision: str | None = "20260822_04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("clinical_notes", sa.Column("treatment_plan", sa.Text(), nullable=True))
    op.add_column("clinical_notes", sa.Column("private_doctor_notes", sa.Text(), nullable=True))
    op.add_column("clinical_notes", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("clinical_notes", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        "UPDATE clinical_notes SET started_at = created_at, completed_at = updated_at "
        "WHERE started_at IS NULL OR completed_at IS NULL"
    )

    op.add_column(
        "prescription_items",
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.create_check_constraint(
        "ck_prescription_items_medication_name_nonblank",
        "prescription_items",
        "length(trim(medication_name)) > 0",
    )
    op.create_check_constraint(
        "ck_prescription_items_dosage_nonblank",
        "prescription_items",
        "length(trim(dosage)) > 0",
    )

    op.add_column("post_visit_summaries", sa.Column("safety_disclaimer", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("post_visit_summaries", "safety_disclaimer")
    op.drop_constraint(
        "ck_prescription_items_dosage_nonblank", "prescription_items", type_="check"
    )
    op.drop_constraint(
        "ck_prescription_items_medication_name_nonblank", "prescription_items", type_="check"
    )
    op.drop_column("prescription_items", "is_active")
    op.drop_column("clinical_notes", "completed_at")
    op.drop_column("clinical_notes", "started_at")
    op.drop_column("clinical_notes", "private_doctor_notes")
    op.drop_column("clinical_notes", "treatment_plan")
