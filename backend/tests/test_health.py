from fastapi.testclient import TestClient


def test_health_endpoint_reports_database_connection(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}

    readiness = client.get("/api/v1/health/ready")
    assert readiness.status_code == 200
    assert readiness.json() == {"status": "ok", "database": "connected"}


def test_liveness_does_not_require_the_database(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
