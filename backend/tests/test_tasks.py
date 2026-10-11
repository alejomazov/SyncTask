from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.task import Task
from app.models.user import User
from app.modules.auth import service as auth_service

ANA = {"email": "ana@example.com", "password": "supersecret1", "full_name": "Ana Soto"}
BEA = {"email": "bea@example.com", "password": "supersecret2", "full_name": "Bea Rojas"}


def login(client: TestClient, credentials: dict[str, str]) -> None:
    client.cookies.clear()
    response = client.post(
        "/auth/login", json={"email": credentials["email"], "password": credentials["password"]}
    )
    assert response.status_code == 200


@pytest.fixture
def ana(db: Session) -> User:
    return auth_service.register_user(db, **ANA)


@pytest.fixture
def ana_client(client: TestClient, ana: User) -> Generator[TestClient, None, None]:
    login(client, ANA)
    yield client


def create(client: TestClient, **fields: object) -> dict:
    response = client.post("/tasks", json={"title": "Preparar informe", **fields})
    assert response.status_code == 201
    return response.json()


def task_actions(db: Session) -> list[str]:
    """Audited task actions, sorted (entries created within the same second have no order)."""
    return sorted(a for a in db.scalars(select(AuditLog.action)) if a.startswith("task."))


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/tasks"),
        ("post", "/tasks"),
        ("patch", "/tasks/00000000-0000-0000-0000-000000000000"),
        ("delete", "/tasks/00000000-0000-0000-0000-000000000000"),
    ],
)
def test_tasks_require_session(client: TestClient, db: Session, method: str, path: str) -> None:
    kwargs = {"json": {"title": "x"}} if method in ("post", "patch") else {}

    assert client.request(method, path, **kwargs).status_code == 401
    assert db.scalars(select(Task)).all() == []


def test_create_task(ana_client: TestClient, ana: User, db: Session) -> None:
    body = create(
        ana_client,
        title="  Preparar informe  ",
        description="Capítulo IV",
        due_at="2026-10-20T18:00:00-03:00",
    )

    assert body["title"] == "Preparar informe"
    assert body["description"] == "Capítulo IV"
    assert body["status"] == "pending"
    assert body["due_at"] is not None
    assert "user_id" not in body
    assert db.scalars(select(Task)).one().user_id == ana.id
    assert task_actions(db) == ["task.created"]


def test_create_task_with_only_a_title(ana_client: TestClient) -> None:
    body = create(ana_client)

    assert body["description"] == ""
    assert body["due_at"] is None


@pytest.mark.parametrize("title", ["", "   ", "x" * 201])
def test_create_task_rejects_invalid_title(ana_client: TestClient, db: Session, title: str) -> None:
    assert ana_client.post("/tasks", json={"title": title}).status_code == 422
    assert db.scalars(select(Task)).all() == []
    assert task_actions(db) == []


def test_create_task_requires_title(ana_client: TestClient) -> None:
    assert ana_client.post("/tasks", json={"description": "sin título"}).status_code == 422


def test_edit_task(ana_client: TestClient, db: Session) -> None:
    task = create(ana_client, due_at="2026-10-20T18:00:00Z")

    response = ana_client.patch(
        f"/tasks/{task['id']}", json={"title": "Revisar informe", "due_at": None}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Revisar informe"
    assert body["due_at"] is None
    assert body["status"] == "pending"
    assert task_actions(db) == ["task.created", "task.updated"]


def test_edit_task_rejects_empty_title_and_keeps_it(ana_client: TestClient) -> None:
    task = create(ana_client)

    assert ana_client.patch(f"/tasks/{task['id']}", json={"title": "  "}).status_code == 422
    assert ana_client.get("/tasks").json()[0]["title"] == "Preparar informe"


def test_edit_task_rejects_unknown_status(ana_client: TestClient) -> None:
    task = create(ana_client)

    assert ana_client.patch(f"/tasks/{task['id']}", json={"status": "archived"}).status_code == 422


def test_null_title_does_not_erase_it(ana_client: TestClient) -> None:
    task = create(ana_client)

    response = ana_client.patch(f"/tasks/{task['id']}", json={"title": None, "status": None})

    assert response.json()["title"] == "Preparar informe"
    assert response.json()["status"] == "pending"


def test_complete_and_reopen_task(ana_client: TestClient, db: Session) -> None:
    task = create(ana_client)

    completed = ana_client.patch(f"/tasks/{task['id']}", json={"status": "completed"})
    assert completed.json()["status"] == "completed"

    reopened = ana_client.patch(f"/tasks/{task['id']}", json={"status": "pending"})
    assert reopened.json()["status"] == "pending"

    assert task_actions(db) == ["task.completed", "task.created", "task.reopened"]


def test_setting_the_same_status_is_not_audited(ana_client: TestClient, db: Session) -> None:
    task = create(ana_client)

    ana_client.patch(f"/tasks/{task['id']}", json={"status": "pending"})

    assert task_actions(db) == ["task.created"]


def test_delete_task(ana_client: TestClient, db: Session) -> None:
    task = create(ana_client)

    assert ana_client.delete(f"/tasks/{task['id']}").status_code == 204

    assert ana_client.get("/tasks").json() == []
    assert db.scalars(select(Task)).all() == []
    assert task_actions(db) == ["task.created", "task.deleted"]
    assert ana_client.delete(f"/tasks/{task['id']}").status_code == 404


def test_list_orders_pending_by_due_date_then_completed(ana_client: TestClient) -> None:
    create(ana_client, title="Sin fecha")
    create(ana_client, title="Más tarde", due_at="2026-10-25T12:00:00Z")
    create(ana_client, title="Pronto", due_at="2026-10-15T12:00:00Z")
    done = create(ana_client, title="Hecha", due_at="2026-10-01T12:00:00Z")
    ana_client.patch(f"/tasks/{done['id']}", json={"status": "completed"})

    titles = [task["title"] for task in ana_client.get("/tasks").json()]

    assert titles == ["Pronto", "Más tarde", "Sin fecha", "Hecha"]


def test_list_filters_by_status(ana_client: TestClient) -> None:
    create(ana_client, title="Pendiente")
    done = create(ana_client, title="Hecha")
    ana_client.patch(f"/tasks/{done['id']}", json={"status": "completed"})

    pending = ana_client.get("/tasks", params={"task_status": "pending"}).json()
    completed = ana_client.get("/tasks", params={"task_status": "completed"}).json()

    assert [task["title"] for task in pending] == ["Pendiente"]
    assert [task["title"] for task in completed] == ["Hecha"]
    assert ana_client.get("/tasks", params={"task_status": "nope"}).status_code == 422


def test_tasks_are_isolated_between_users(client: TestClient, ana: User, db: Session) -> None:
    login(client, ANA)
    task = create(client)

    auth_service.register_user(db, **BEA)
    login(client, BEA)

    assert client.get("/tasks").json() == []
    assert client.patch(f"/tasks/{task['id']}", json={"title": "Ajena"}).status_code == 404
    assert client.delete(f"/tasks/{task['id']}").status_code == 404

    login(client, ANA)
    assert [t["title"] for t in client.get("/tasks").json()] == ["Preparar informe"]
