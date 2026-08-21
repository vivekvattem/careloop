from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User, UserRole
from tests.conftest import TestingSessionLocal


def register(client: TestClient, payload: dict[str, str]) -> dict[str, object]:
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    return response.json()


def login(client: TestClient, email: str, password: str):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def test_successful_patient_registration(client: TestClient, patient_payload: dict[str, str]) -> None:
    body = register(client, patient_payload)

    assert body["email"] == "alex@example.com"
    assert body["role"] == "patient"
    assert body["is_active"] is True


def test_public_registration_cannot_choose_privileged_role(
    client: TestClient, patient_payload: dict[str, str]
) -> None:
    patient_payload["role"] = "admin"

    body = register(client, patient_payload)

    assert body["role"] == "patient"


def test_duplicate_email_is_rejected(client: TestClient, patient_payload: dict[str, str]) -> None:
    register(client, patient_payload)
    patient_payload["email"] = "ALEX@example.com"

    response = client.post("/api/v1/auth/register", json=patient_payload)

    assert response.status_code == 409


def test_email_is_normalized(client: TestClient, patient_payload: dict[str, str]) -> None:
    patient_payload["email"] = "Alex.Patient@EXAMPLE.COM"

    body = register(client, patient_payload)

    assert body["email"] == "alex.patient@example.com"


def test_password_is_hashed_in_database(client: TestClient, patient_payload: dict[str, str]) -> None:
    register(client, patient_payload)
    with TestingSessionLocal() as db:
        user = db.scalar(select(User).where(User.email == patient_payload["email"]))

    assert user is not None
    assert user.password_hash != patient_payload["password"]
    assert verify_password(patient_payload["password"], user.password_hash)


def test_successful_login(client: TestClient, patient_payload: dict[str, str]) -> None:
    register(client, patient_payload)

    response = login(client, patient_payload["email"], patient_payload["password"])

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert response.json()["access_token"]
    assert client.cookies.get("careloop_refresh")


def test_invalid_password_is_rejected(client: TestClient, patient_payload: dict[str, str]) -> None:
    register(client, patient_payload)

    response = login(client, patient_payload["email"], "WrongPassword123")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_me_with_valid_access_token(client: TestClient, patient_payload: dict[str, str]) -> None:
    register(client, patient_payload)
    token = login(client, patient_payload["email"], patient_payload["password"]).json()[
        "access_token"
    ]

    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["email"] == patient_payload["email"]


def test_me_without_token_is_rejected(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401


def test_refresh_token_flow(client: TestClient, patient_payload: dict[str, str]) -> None:
    register(client, patient_payload)
    login(client, patient_payload["email"], patient_payload["password"])

    response = client.post("/api/v1/auth/refresh")

    assert response.status_code == 200
    assert response.json()["access_token"]


def test_logout_clears_refresh_session(client: TestClient, patient_payload: dict[str, str]) -> None:
    register(client, patient_payload)
    login(client, patient_payload["email"], patient_payload["password"])

    logout_response = client.post("/api/v1/auth/logout")
    refresh_response = client.post("/api/v1/auth/refresh")

    assert logout_response.status_code == 204
    assert refresh_response.status_code == 401


def test_refresh_token_cannot_access_me(client: TestClient, patient_payload: dict[str, str]) -> None:
    register(client, patient_payload)
    login(client, patient_payload["email"], patient_payload["password"])
    refresh_token = client.cookies.get("careloop_refresh")

    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {refresh_token}"}
    )

    assert response.status_code == 401


def test_access_token_cannot_refresh(client: TestClient, patient_payload: dict[str, str]) -> None:
    register(client, patient_payload)
    access_token = login(
        client, patient_payload["email"], patient_payload["password"]
    ).json()["access_token"]
    client.cookies.clear()
    client.cookies.set("careloop_refresh", access_token, path="/api/v1/auth")

    response = client.post("/api/v1/auth/refresh")

    assert response.status_code == 401


def test_patient_role_access_and_rejections(
    client: TestClient, patient_payload: dict[str, str]
) -> None:
    register(client, patient_payload)
    token = login(client, patient_payload["email"], patient_payload["password"]).json()[
        "access_token"
    ]
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/api/v1/auth/role/patient", headers=headers).status_code == 200
    assert client.get("/api/v1/auth/role/doctor", headers=headers).status_code == 403
    assert client.get("/api/v1/auth/role/admin", headers=headers).status_code == 403


def test_admin_route_rejects_doctor(client: TestClient) -> None:
    with TestingSessionLocal() as db:
        doctor = User(
            full_name="Dana Doctor",
            email="doctor@example.com",
            password_hash=hash_password("StrongPass123"),
            role=UserRole.DOCTOR,
        )
        db.add(doctor)
        db.commit()
        db.refresh(doctor)
        token = create_access_token(doctor)

    response = client.get(
        "/api/v1/auth/role/admin", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 403


def test_protected_role_route_rejects_unauthenticated_request(client: TestClient) -> None:
    response = client.get("/api/v1/auth/role/patient")

    assert response.status_code == 401


def test_password_hash_never_appears_in_api_responses(
    client: TestClient, patient_payload: dict[str, str]
) -> None:
    registration = client.post("/api/v1/auth/register", json=patient_payload)
    login_response = login(client, patient_payload["email"], patient_payload["password"])
    token = login_response.json()["access_token"]
    me_response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )

    for response in (registration, login_response, me_response):
        assert "password_hash" not in response.text
        assert patient_payload["password"] not in response.text
