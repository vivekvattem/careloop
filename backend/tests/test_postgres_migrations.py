import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from tests.test_postgres_concurrency import _postgres_url

pytestmark = pytest.mark.postgresql


def test_phase_2b_migration_downgrade_and_upgrade_in_isolated_schema() -> None:
    database_url = _postgres_url()
    if not database_url or not database_url.startswith("postgresql"):
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL migration tests")

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

            command.downgrade(alembic_config, "20260822_02")
            assert not inspect(connection).has_table("appointments", schema=schema)
            assert not inspect(connection).has_table("slot_holds", schema=schema)
            assert inspect(connection).has_table("users", schema=schema)
            assert inspect(connection).has_table("doctor_profiles", schema=schema)

            command.upgrade(alembic_config, "head")
            assert inspect(connection).has_table("appointments", schema=schema)
            assert inspect(connection).has_table("symptom_submissions", schema=schema)
    finally:
        migration_engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin_engine.dispose()
