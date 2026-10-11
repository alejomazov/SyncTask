from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.auth import service

COOKIE = get_settings().auth_cookie_name
USER = {"email": "ana@example.com", "password": "supersecret1", "full_name": "Ana Soto"}


def register(client: TestClient, **overrides: str):
    return client.post("/auth/register", json={**USER, **overrides})


def test_register_creates_user_and_session(client: TestClient) -> None:
    response = register(client)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == USER["email"]
    assert body["role"] == "user"
    assert body["is_active"] is True
    assert "hashed_password" not in body and "password" not in body
    assert "httponly" in response.headers["set-cookie"].lower()
    assert client.get("/auth/me").status_code == 200


def test_register_stores_hashed_password(client: TestClient, db: Session) -> None:
    register(client)

    user = service.get_user_by_email(db, USER["email"])
    assert user is not None
    assert user.hashed_password != USER["password"]


def test_register_rejects_duplicate_email(client: TestClient) -> None:
    register(client)

    assert register(client, email="ANA@example.com").status_code == 409


def test_register_rejects_short_password(client: TestClient) -> None:
    assert register(client, password="short").status_code == 422


def test_login_sets_session_cookie(client: TestClient) -> None:
    register(client)
    client.cookies.clear()

    response = client.post(
        "/auth/login", json={"email": USER["email"], "password": USER["password"]}
    )

    assert response.status_code == 200
    assert COOKIE in response.cookies
    assert client.get("/auth/me").json()["email"] == USER["email"]


def test_login_rejects_wrong_password(client: TestClient) -> None:
    register(client)
    client.cookies.clear()

    response = client.post("/auth/login", json={"email": USER["email"], "password": "wrong-pass"})

    assert response.status_code == 401
    assert COOKIE not in response.cookies


def test_login_rejects_unknown_email(client: TestClient) -> None:
    response = client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "whatever1"}
    )

    assert response.status_code == 401


def test_login_rejects_disabled_account(client: TestClient, db: Session) -> None:
    register(client)
    client.cookies.clear()
    user = service.get_user_by_email(db, USER["email"])
    assert user is not None
    user.is_active = False
    db.commit()

    response = client.post(
        "/auth/login", json={"email": USER["email"], "password": USER["password"]}
    )

    assert response.status_code == 403


def test_disabled_account_loses_existing_session(client: TestClient, db: Session) -> None:
    register(client)
    user = service.get_user_by_email(db, USER["email"])
    assert user is not None
    user.is_active = False
    db.commit()

    assert client.get("/auth/me").status_code == 401


def test_me_requires_session(client: TestClient) -> None:
    assert client.get("/auth/me").status_code == 401


def test_me_rejects_tampered_token(client: TestClient) -> None:
    client.cookies.set(COOKIE, "not-a-valid-token")

    assert client.get("/auth/me").status_code == 401


def test_logout_clears_session(client: TestClient) -> None:
    register(client)

    assert client.post("/auth/logout").status_code == 204
    assert client.get("/auth/me").status_code == 401
