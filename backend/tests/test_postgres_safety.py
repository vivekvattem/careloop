import pytest

import tests.test_postgres_concurrency as postgres_tests


def test_postgresql_tests_refuse_development_database_url(monkeypatch) -> None:
    shared = "postgresql+psycopg://careloop:test@localhost:5432/careloop"
    monkeypatch.setenv("TEST_DATABASE_URL", shared)
    monkeypatch.setenv("DATABASE_URL", shared)
    monkeypatch.delenv("CARELOOP_DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="must not equal"):
        postgres_tests._postgres_url()
