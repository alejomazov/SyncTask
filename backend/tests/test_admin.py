import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import User, UserRole
from app.modules.auth import service

ADMIN = {"email": "admin@example.com", "password": "admin-secret-1", "full_name": "Admin"}
USER = {"email": "ana@example.com", "password": "supersecret1", "full_name": "Ana Soto"}


def login(client: TestClient, credentials: dict[str, str]) -> None:
    client.cookies.clear()
    response = client.post(
        "/auth/login", json={"email": credentials["email"], "password": credentials["password"]}
    )
    assert response.status_code == 200


@pytest.fixture
def admin(db: Session) -> User:
    return service.register_user(db, **ADMIN, role=UserRole.ADMIN)


@pytest.fixture
def user(db: Session) -> User:
    return service.register_user(db, **USER)


@pytest.fixture
def admin_client(client: TestClient, admin: User) -> TestClient:
    login(client, ADMIN)
    return client


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/admin/users"),
        ("get", "/admin/audit-logs"),
        ("patch", "/admin/users/00000000-0000-0000-0000-000000000000"),
    ],
)
def test_admin_routes_reject_anonymous_and_regular_users(
    client: TestClient, user: User, method: str, path: str
) -> None:
    kwargs = {"json": {"is_active": False}} if method == "patch" else {}

    assert client.request(method, path, **kwargs).status_code == 401

    login(client, USER)
    assert client.request(method, path, **kwargs).status_code == 403


def test_list_users(admin_client: TestClient, user: User) -> None:
    response = admin_client.get("/admin/users")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert {item["email"] for item in body["items"]} == {ADMIN["email"], USER["email"]}
    assert all("hashed_password" not in item for item in body["items"])


def test_list_users_search_and_pagination(admin_client: TestClient, user: User) -> None:
    found = admin_client.get("/admin/users", params={"search": "soto"}).json()
    assert [item["email"] for item in found["items"]] == [USER["email"]]

    paged = admin_client.get("/admin/users", params={"page_size": 1, "page": 2}).json()
    assert paged["total"] == 2
    assert len(paged["items"]) == 1


def test_disable_and_enable_user(admin_client: TestClient, user: User) -> None:
    disabled = admin_client.patch(f"/admin/users/{user.id}", json={"is_active": False})
    assert disabled.status_code == 200
    assert disabled.json()["is_active"] is False

    admin_client.cookies.clear()
    blocked = admin_client.post(
        "/auth/login", json={"email": USER["email"], "password": USER["password"]}
    )
    assert blocked.status_code == 403

    login(admin_client, ADMIN)
    enabled = admin_client.patch(f"/admin/users/{user.id}", json={"is_active": True})
    assert enabled.json()["is_active"] is True
    login(admin_client, USER)


def test_admin_cannot_disable_own_account(admin_client: TestClient, admin: User) -> None:
    response = admin_client.patch(f"/admin/users/{admin.id}", json={"is_active": False})

    assert response.status_code == 409
    assert admin_client.get("/auth/me").status_code == 200


def test_update_unknown_user_returns_404(admin_client: TestClient) -> None:
    response = admin_client.patch(
        "/admin/users/00000000-0000-0000-0000-000000000000", json={"is_active": False}
    )

    assert response.status_code == 404


def test_auth_events_are_audited(client: TestClient, admin: User) -> None:
    client.post("/auth/register", json=USER)
    client.post("/auth/logout")
    client.post("/auth/login", json={"email": USER["email"], "password": "wrong-pass"})
    login(client, ADMIN)

    logs = client.get("/admin/audit-logs", params={"page_size": 100}).json()["items"]
    actions = [log["action"] for log in logs]

    assert actions.count("auth.register") == 1
    assert actions.count("auth.logout") == 1
    assert actions.count("auth.login_failed") == 1
    assert actions.count("auth.login") == 1
    failed = next(log for log in logs if log["action"] == "auth.login_failed")
    assert failed["detail"] == {"email": USER["email"], "reason": "invalid_credentials"}
    assert "password" not in str(logs)


def test_status_changes_are_audited(admin_client: TestClient, admin: User, user: User) -> None:
    admin_client.patch(f"/admin/users/{user.id}", json={"is_active": False})
    admin_client.patch(f"/admin/users/{user.id}", json={"is_active": True})

    disabled = admin_client.get(
        "/admin/audit-logs", params={"action": "admin.user_disabled"}
    ).json()
    assert disabled["total"] == 1
    entry = disabled["items"][0]
    assert entry["actor_email"] == ADMIN["email"]
    assert entry["target_type"] == "user"
    assert entry["target_id"] == str(user.id)

    enabled = admin_client.get("/admin/audit-logs", params={"action": "admin.user_enabled"}).json()
    assert enabled["total"] == 1


def test_audit_logs_filter_by_actor_email(admin_client: TestClient, user: User) -> None:
    login(admin_client, USER)
    login(admin_client, ADMIN)

    response = admin_client.get("/admin/audit-logs", params={"actor_email": "ana@"}).json()

    assert response["total"] == 1
    assert response["items"][0]["actor_email"] == USER["email"]


def test_audit_logs_reject_unknown_action(admin_client: TestClient) -> None:
    assert admin_client.get("/admin/audit-logs", params={"action": "nope"}).status_code == 422
