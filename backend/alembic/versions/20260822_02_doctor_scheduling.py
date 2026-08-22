"""Add doctor profiles, working hours, and leave.

Revision ID: 20260822_02
Revises: 20260822_01
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260822_02"
down_revision: str | None = "20260822_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "doctor_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("specialisation", sa.String(length=120), nullable=False),
        sa.Column(
            "qualifications", sa.String(length=500), server_default="", nullable=False
        ),
        sa.Column("biography", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "consultation_mode",
            sa.String(length=80),
            server_default="in_person",
            nullable=False,
        ),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column(
            "slot_duration_minutes", sa.Integer(), server_default="30", nullable=False
        ),
        sa.Column(
            "timezone", sa.String(length=64), server_default="Asia/Kolkata", nullable=False
        ),
        sa.Column(
            "is_available_for_booking", sa.Boolean(), server_default=sa.true(), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "slot_duration_minutes BETWEEN 5 AND 180",
            name=op.f("ck_doctor_profiles_slot_duration_range"),
        ),
        sa.CheckConstraint(
            "length(trim(specialisation)) > 0",
            name=op.f("ck_doctor_profiles_specialisation_not_blank"),
        ),
        sa.CheckConstraint(
            "consultation_mode IN ('in_person', 'video', 'hybrid')",
            name=op.f("ck_doctor_profiles_valid_consultation_mode"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_doctor_profiles_user_id_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_doctor_profiles")),
        sa.UniqueConstraint("user_id", name=op.f("uq_doctor_profiles_user_id")),
    )
    op.create_index(
        op.f("ix_doctor_profiles_specialisation"),
        "doctor_profiles",
        ["specialisation"],
        unique=False,
    )

    op.create_table(
        "doctor_working_hours",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("doctor_profile_id", sa.Uuid(), nullable=False),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "day_of_week BETWEEN 0 AND 6",
            name=op.f("ck_doctor_working_hours_valid_day_of_week"),
        ),
        sa.CheckConstraint(
            "start_time < end_time",
            name=op.f("ck_doctor_working_hours_start_before_end"),
        ),
        sa.ForeignKeyConstraint(
            ["doctor_profile_id"],
            ["doctor_profiles.id"],
            name=op.f("fk_doctor_working_hours_doctor_profile_id_doctor_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_doctor_working_hours")),
        sa.UniqueConstraint(
            "doctor_profile_id",
            "day_of_week",
            "start_time",
            "end_time",
            name="uq_doctor_working_hours_interval",
        ),
    )
    op.create_index(
        "ix_doctor_working_hours_profile_weekday",
        "doctor_working_hours",
        ["doctor_profile_id", "day_of_week"],
        unique=False,
    )

    op.create_table(
        "doctor_leaves",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("doctor_profile_id", sa.Uuid(), nullable=False),
        sa.Column("leave_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["doctor_profile_id"],
            ["doctor_profiles.id"],
            name=op.f("fk_doctor_leaves_doctor_profile_id_doctor_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_doctor_leaves")),
        sa.UniqueConstraint(
            "doctor_profile_id",
            "leave_date",
            name="uq_doctor_leaves_profile_date",
        ),
    )


def downgrade() -> None:
    op.drop_table("doctor_leaves")
    op.drop_index(
        "ix_doctor_working_hours_profile_weekday",
        table_name="doctor_working_hours",
    )
    op.drop_table("doctor_working_hours")
    op.drop_index(op.f("ix_doctor_profiles_specialisation"), table_name="doctor_profiles")
    op.drop_table("doctor_profiles")

