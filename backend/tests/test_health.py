from fastapi.testclient import TestClient


def test_health_endpoint_reports_database_connection(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}

