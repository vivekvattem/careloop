import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from tests.test_postgres_concurrency import _postgres_url

pytestmark = pytest.mark.postgresql


def test_phase_3_migration_downgrade_and_upgrade_in_isolated_schema() -> None:
    database_url = _postgres_url()
    if not database_url or not database_url.startswith("postgresql"):
        pytest.skip("Set a dedicated TEST_DATABASE_URL to run PostgreSQL migration tests")

    schema = f"careloop_migration_test_{uuid.uuid4().hex}"
    admin_engine = create_engine(database_url)
    with admin_engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
        connection.execute(text(f"CREATE SCHEMA {schema}"))

    scoped_url = make_url(database_url).update_query_dict(
        {"options": f"-csearch_path={schema},public"}
    )
    migration_engine = create_engine(scoped_url)
    alembic_config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    alembic_config.attributes["version_table_schema"] = schema

    try:
        with migration_engine.connect() as connection:
            alembic_config.attributes["connection"] = connection
            command.upgrade(alembic_config, "head")
            assert inspect(connection).has_table("appointments", schema=schema)
            assert inspect(connection).has_table("users", schema=schema)

            command.downgrade(alembic_config, "20260822_03")
            assert not inspect(connection).has_table("clinical_notes", schema=schema)
            assert not inspect(connection).has_table("pre_visit_summaries", schema=schema)
            assert inspect(connection).has_table("users", schema=schema)
            assert inspect(connection).has_table("appointments", schema=schema)

            patient_id, doctor_user_id, profile_id, appointment_id = [uuid.uuid4() for _ in range(4)]
            now = datetime.now(timezone.utc)
            connection.execute(
                text(
                    "INSERT INTO users (id, full_name, email, password_hash, role, is_active) "
                    "VALUES (:patient_id, 'Migration Patient', :patient_email, 'unused', 'patient', true), "
                    "(:doctor_id, 'Migration Doctor', :doctor_email, 'unused', 'doctor', true)"
                ),
                {
                    "patient_id": patient_id,
                    "patient_email": f"patient-{patient_id}@example.com",
                    "doctor_id": doctor_user_id,
                    "doctor_email": f"doctor-{doctor_user_id}@example.com",
                },
            )
            connection.execute(
                text(
                    "INSERT INTO doctor_profiles (id, user_id, specialisation) "
                    "VALUES (:id, :user_id, 'Migration Medicine')"
                ),
                {"id": profile_id, "user_id": doctor_user_id},
            )
            connection.execute(
                text(
                    "INSERT INTO appointments "
                    "(id, patient_user_id, doctor_profile_id, slot_start, slot_end, status) "
                    "VALUES (:id, :patient_id, :doctor_id, :start, :end, 'confirmed')"
                ),
                {
                    "id": appointment_id,
                    "patient_id": patient_id,
                    "doctor_id": profile_id,
                    "start": now,
                    "end": now + timedelta(minutes=30),
                },
            )
            connection.execute(
                text(
                    "INSERT INTO symptom_submissions "
                    "(id, appointment_id, chief_complaint, symptom_description, duration, severity) "
                    "VALUES (:id, :appointment_id, 'Migration symptom', "
                    "'Fictional migration symptom description', 'Two days', 4)"
                ),
                {"id": uuid.uuid4(), "appointment_id": appointment_id},
            )

            command.upgrade(alembic_config, "head")
            assert inspect(connection).has_table("clinical_notes", schema=schema)
            assert inspect(connection).has_table("care_documents", schema=schema)
            assert connection.scalar(text("SELECT count(*) FROM pre_visit_summaries")) == 1
            assert connection.scalar(text("SELECT count(*) FROM care_documents")) == 1
    finally:
        migration_engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin_engine.dispose()
