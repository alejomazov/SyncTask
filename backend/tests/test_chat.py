import contextlib
import json
from collections.abc import Generator
from typing import Any

import anthropic
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.controllers.chat import get_session_factory
from app.integrations.anthropic import client as anthropic_client
from app.main import app
from app.models.audit_log import AuditLog
from app.models.interaction import Interaction
from app.models.task import Task
from app.models.user import User
from app.modules.ai import assistant
from app.modules.auth import service as auth_service
from tests.fake_anthropic import FakeAnthropic, api_error, connection_error, reply

ANA = {"email": "ana@example.com", "password": "supersecret1", "full_name": "Ana Soto"}
BEA = {"email": "bea@example.com", "password": "supersecret2", "full_name": "Bea Rojas"}
VALID_KEY = "sk-ant-valid-key-0000000000001234"
NEW_TASK = {"title": "Preparar informe", "description": None, "due_at": None}
MISSING_ID = "00000000-0000-0000-0000-000000000000"


def login(client: TestClient, credentials: dict[str, str]) -> None:
    client.cookies.clear()
    response = client.post(
        "/auth/login", json={"email": credentials["email"], "password": credentials["password"]}
    )
    assert response.status_code == 200


@pytest.fixture
def fake_claude(monkeypatch: pytest.MonkeyPatch) -> FakeAnthropic:
    fake = FakeAnthropic()
    monkeypatch.setattr(anthropic_client, "_client_factory", fake.for_key)
    return fake


@pytest.fixture
def ana(db: Session) -> User:
    return auth_service.register_user(db, **ANA)


@pytest.fixture
def chat(
    client: TestClient, ana: User, db: Session, fake_claude: FakeAnthropic
) -> Generator[TestClient, None, None]:
    """Client logged in as Ana, with a Claude key configured."""
    app.dependency_overrides[get_session_factory] = lambda: lambda: contextlib.nullcontext(db)
    login(client, ANA)
    assert client.put("/settings/ai-key", json={"api_key": VALID_KEY}).status_code == 200
    yield client


def send(client: TestClient, message: str = "Hola", **extra: Any) -> list[dict[str, Any]]:
    """Send an instruction and return the events of the streamed reply."""
    response = client.post("/chat/messages", json={"message": message, **extra})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = []
    for chunk in response.text.strip().split("\n\n"):
        event_line, data_line = chunk.split("\n", 1)
        event = json.loads(data_line.removeprefix("data: "))
        assert event_line == f"event: {event['type']}"
        events.append(event)
    return events


def of_type(events: list[dict[str, Any]], event_type: str) -> list[dict[str, Any]]:
    return [event for event in events if event["type"] == event_type]


def reply_text(events: list[dict[str, Any]]) -> str:
    return "".join(event["delta"] for event in of_type(events, "text"))


def tool_results(request: dict[str, Any]) -> list[dict[str, Any]]:
    """Tool results sent back to the model in the last message of a request."""
    return request["messages"][-1]["content"]


def audit_actions(db: Session) -> list[str]:
    return sorted(db.scalars(select(AuditLog.action)))


def set_mode(client: TestClient, mode: str) -> None:
    assert client.patch("/settings", json={"execution_mode": mode}).status_code == 200


def pending_action(events: list[dict[str, Any]]) -> tuple[str, str]:
    [event] = of_type(events, "action")
    assert event["action"]["status"] == "pending"
    return event["interaction_id"], event["action"]["id"]


# --- Access ----------------------------------------------------------------------


def test_chat_requires_session(client: TestClient) -> None:
    assert client.post("/chat/messages", json={"message": "Hola"}).status_code == 401
    assert client.get("/chat/interactions").status_code == 401
    assert client.post("/chat/conversation/reset").status_code == 401


def test_chat_requires_a_configured_key(
    client: TestClient, ana: User, fake_claude: FakeAnthropic
) -> None:
    login(client, ANA)

    assert client.post("/chat/messages", json={"message": "Hola"}).status_code == 409
    assert fake_claude.requests == []


def test_empty_message_is_rejected(chat: TestClient, fake_claude: FakeAnthropic) -> None:
    assert chat.post("/chat/messages", json={"message": "   "}).status_code == 422
    assert fake_claude.requests == []


# --- Conversation ----------------------------------------------------------------


def test_reply_is_streamed_and_stored(
    chat: TestClient, db: Session, fake_claude: FakeAnthropic
) -> None:
    fake_claude.script = [reply("Hola Ana, ¿en qué te ayudo?")]

    events = send(chat, "Hola")

    assert len(of_type(events, "text")) == 2
    assert reply_text(events) == "Hola Ana, ¿en qué te ayudo?"
    assert events[-1]["type"] == "done"

    interaction = db.scalars(select(Interaction)).one()
    assert str(interaction.id) == events[-1]["interaction_id"]
    assert interaction.instruction == "Hola"
    assert interaction.response == "Hola Ana, ¿en qué te ayudo?"
    assert interaction.actions == []
    assert interaction.status == "completed"


def test_request_sent_to_claude(chat: TestClient, fake_claude: FakeAnthropic) -> None:
    fake_claude.script = [reply("Listo")]

    send(chat, "¿Qué tengo hoy?", timezone="America/Santiago")

    [request] = fake_claude.requests
    assert fake_claude.keys_used[-1] == VALID_KEY
    assert request["model"] == "claude-opus-5-5"
    assert request["thinking"] == {"type": "adaptive"}
    assert request["output_config"] == {"effort": "medium"}
    assert request["messages"] == [{"role": "user", "content": "¿Qué tengo hoy?"}]
    assert "Ana Soto" in request["system"]
    assert "America/Santiago" in request["system"]
    assert "confirmar" in request["system"]
    assert VALID_KEY not in request["system"]
    for tool in request["tools"]:
        assert tool["strict"] is True
        assert tool["input_schema"]["additionalProperties"] is False
        assert tool["input_schema"]["required"] == list(tool["input_schema"]["properties"])
    assert "temperature" not in request


def test_unknown_timezone_falls_back_to_utc(chat: TestClient, fake_claude: FakeAnthropic) -> None:
    fake_claude.script = [reply("Listo")]

    send(chat, "Hola", timezone="Mars/Olympus")

    assert "zona horaria UTC" in fake_claude.requests[0]["system"]


def test_conversation_history_is_sent_and_can_be_reset(
    chat: TestClient, fake_claude: FakeAnthropic
) -> None:
    fake_claude.script = [reply("Primera respuesta"), reply("Segunda respuesta"), reply("Nueva")]

    send(chat, "Primera")
    send(chat, "Segunda")
    assert fake_claude.requests[1]["messages"] == [
        {"role": "user", "content": "Primera"},
        {"role": "assistant", "content": "Primera respuesta"},
        {"role": "user", "content": "Segunda"},
    ]
    assert len(chat.get("/chat/interactions").json()) == 2

    assert chat.post("/chat/conversation/reset").status_code == 204
    send(chat, "Tercera")

    assert fake_claude.requests[2]["messages"] == [{"role": "user", "content": "Tercera"}]
    assert [i["instruction"] for i in chat.get("/chat/interactions").json()] == ["Tercera"]
    history = chat.get("/chat/interactions", params={"scope": "all"}).json()
    assert [i["instruction"] for i in history] == ["Primera", "Segunda", "Tercera"]


# --- Read-only tools -------------------------------------------------------------


def test_read_tool_runs_immediately_and_feeds_the_model(
    chat: TestClient, db: Session, fake_claude: FakeAnthropic
) -> None:
    chat.post("/tasks", json={"title": "Comprar pan"})
    fake_claude.script = [
        reply("Reviso tus tareas.", [("list_tasks", {"status": "pending"})]),
        reply("Tienes una tarea: Comprar pan."),
    ]

    events = send(chat, "¿Qué tareas tengo?")

    assert of_type(events, "status") == [{"type": "status", "tool": "list_tasks"}]
    assert of_type(events, "action") == []
    assert reply_text(events) == "Reviso tus tareas.\n\nTienes una tarea: Comprar pan."

    second = fake_claude.requests[1]
    assert [message["role"] for message in second["messages"]] == ["user", "assistant", "user"]
    [result] = tool_results(second)
    assert result["type"] == "tool_result"
    assert result["tool_use_id"] == "toolu_list_tasks_0"
    assert "is_error" not in result
    assert [task["title"] for task in json.loads(result["content"])["tasks"]] == ["Comprar pan"]
    # The assistant turn goes back unchanged, thinking blocks included.
    assert [block.type for block in second["messages"][1]["content"]] == [
        "thinking",
        "text",
        "tool_use",
    ]
    assert db.scalars(select(Interaction)).one().actions == []


def test_calendar_tool_without_connected_accounts(
    chat: TestClient, fake_claude: FakeAnthropic
) -> None:
    call = {"start": "2026-10-12T00:00:00-03:00", "end": "2026-10-13T00:00:00-03:00"}
    fake_claude.script = [reply("", [("get_calendar_events", call)]), reply("No hay cuentas.")]

    send(chat, "¿Qué tengo mañana?")

    result = json.loads(tool_results(fake_claude.requests[1])[0]["content"])
    assert result["events"] == []
    assert "no connected calendar accounts" in result["note"]


# --- Confirm mode ----------------------------------------------------------------


def test_confirm_mode_holds_the_action(
    chat: TestClient, db: Session, fake_claude: FakeAnthropic
) -> None:
    fake_claude.script = [
        reply("", [("create_task", NEW_TASK)]),
        reply("Te propuse crear la tarea; confírmala en la tarjeta."),
    ]

    events = send(chat, "Crea una tarea para preparar el informe")

    [event] = of_type(events, "action")
    assert event["action"]["tool"] == "create_task"
    assert event["action"]["status"] == "pending"
    assert event["action"]["summary"] == "Crear la tarea «Preparar informe»"
    assert db.scalars(select(Task)).all() == []

    [result] = tool_results(fake_claude.requests[1])
    assert json.loads(result["content"])["status"] == "pending_confirmation"
    assert "ai.action_proposed" in audit_actions(db)
    assert "task.created" not in audit_actions(db)

    [stored] = chat.get("/chat/interactions").json()
    assert stored["actions"][0]["status"] == "pending"


def test_confirming_executes_the_action(
    chat: TestClient, db: Session, fake_claude: FakeAnthropic
) -> None:
    due = "2026-10-20T15:00:00-03:00"
    fake_claude.script = [
        reply("", [("create_task", {**NEW_TASK, "description": "Cap. IV", "due_at": due})]),
        reply("Confírmala."),
    ]
    interaction_id, action_id = pending_action(
        send(chat, "Crea la tarea", timezone="America/Santiago")
    )

    response = chat.post(f"/chat/interactions/{interaction_id}/actions/{action_id}/confirm")

    assert response.status_code == 200
    assert response.json()["actions"][0]["status"] == "executed"
    task = db.scalars(select(Task)).one()
    assert task.title == "Preparar informe"
    assert task.description == "Cap. IV"
    assert task.due_at is not None
    assert "task.created" in audit_actions(db)
    created = db.scalars(select(AuditLog).where(AuditLog.action == "task.created")).one()
    assert created.detail == {"title": "Preparar informe", "via": "assistant"}

    again = chat.post(f"/chat/interactions/{interaction_id}/actions/{action_id}/confirm")
    assert again.status_code == 409
    assert len(db.scalars(select(Task)).all()) == 1


def test_summary_shows_the_due_date_in_the_user_timezone(
    chat: TestClient, fake_claude: FakeAnthropic
) -> None:
    fake_claude.script = [
        reply("", [("create_task", {**NEW_TASK, "due_at": "2026-10-20T18:00:00Z"})]),
        reply("Confírmala."),
    ]

    events = send(chat, "Crea la tarea", timezone="America/Santiago")

    summary = of_type(events, "action")[0]["action"]["summary"]
    assert summary == "Crear la tarea «Preparar informe», con fecha límite 20-10-2026 15:00"


def test_discarding_changes_nothing(
    chat: TestClient, db: Session, fake_claude: FakeAnthropic
) -> None:
    fake_claude.script = [reply("", [("create_task", NEW_TASK)]), reply("Confírmala.")]
    interaction_id, action_id = pending_action(send(chat, "Crea la tarea"))

    response = chat.post(f"/chat/interactions/{interaction_id}/actions/{action_id}/discard")

    assert response.status_code == 200
    assert response.json()["actions"][0]["status"] == "discarded"
    assert db.scalars(select(Task)).all() == []
    assert "ai.action_discarded" in audit_actions(db)
    confirm = chat.post(f"/chat/interactions/{interaction_id}/actions/{action_id}/confirm")
    assert confirm.status_code == 409


def test_action_state_is_given_to_the_model_on_the_next_turn(
    chat: TestClient, fake_claude: FakeAnthropic
) -> None:
    fake_claude.script = [
        reply("", [("create_task", NEW_TASK)]),
        reply("Confírmala."),
        reply("Entendido."),
    ]
    interaction_id, action_id = pending_action(send(chat, "Crea la tarea"))
    chat.post(f"/chat/interactions/{interaction_id}/actions/{action_id}/discard")

    send(chat, "Mejor no")

    assert (
        "- Crear la tarea «Preparar informe»: descartada por el usuario"
        in fake_claude.requests[2]["system"]
    )


def test_confirming_fails_cleanly_when_the_task_is_gone(
    chat: TestClient, db: Session, fake_claude: FakeAnthropic
) -> None:
    task_id = chat.post("/tasks", json={"title": "Comprar pan"}).json()["id"]
    fake_claude.script = [
        reply("", [("set_task_status", {"task_id": task_id, "status": "completed"})]),
        reply("Confírmala."),
    ]
    events = send(chat, "Completa comprar pan")
    assert of_type(events, "action")[0]["action"]["summary"] == "Completar la tarea «Comprar pan»"
    interaction_id, action_id = pending_action(events)
    chat.delete(f"/tasks/{task_id}")

    response = chat.post(f"/chat/interactions/{interaction_id}/actions/{action_id}/confirm")

    assert response.status_code == 200
    assert response.json()["actions"][0]["status"] == "failed"


def test_user_cannot_confirm_another_users_action(
    chat: TestClient, db: Session, fake_claude: FakeAnthropic
) -> None:
    fake_claude.script = [reply("", [("create_task", NEW_TASK)]), reply("Confírmala.")]
    interaction_id, action_id = pending_action(send(chat, "Crea la tarea"))

    auth_service.register_user(db, **BEA)
    login(chat, BEA)

    path = f"/chat/interactions/{interaction_id}/actions/{action_id}"
    assert chat.post(f"{path}/confirm").status_code == 404
    assert chat.post(f"{path}/discard").status_code == 404
    assert chat.get("/chat/interactions", params={"scope": "all"}).json() == []
    assert db.scalars(select(Task)).all() == []


# --- Automatic mode --------------------------------------------------------------


def test_automatic_mode_executes_immediately(
    chat: TestClient, db: Session, fake_claude: FakeAnthropic
) -> None:
    set_mode(chat, "automatic")
    fake_claude.script = [reply("", [("create_task", NEW_TASK)]), reply("Creé la tarea.")]

    events = send(chat, "Crea la tarea")

    assert of_type(events, "action")[0]["action"]["status"] == "executed"
    assert db.scalars(select(Task)).one().title == "Preparar informe"
    result = json.loads(tool_results(fake_claude.requests[1])[0]["content"])
    assert result["status"] == "executed"
    assert result["task"]["title"] == "Preparar informe"
    assert "automático" in fake_claude.requests[0]["system"]


def test_automatic_mode_edits_and_completes(
    chat: TestClient, db: Session, fake_claude: FakeAnthropic
) -> None:
    set_mode(chat, "automatic")
    task_id = chat.post(
        "/tasks", json={"title": "Comprar pan", "due_at": "2026-10-20T15:00:00Z"}
    ).json()["id"]
    update = {
        "task_id": task_id,
        "title": "Comprar pan integral",
        "description": None,
        "due_at": None,
        "clear_due_date": True,
    }
    fake_claude.script = [
        reply(
            "",
            [
                ("update_task", update),
                ("set_task_status", {"task_id": task_id, "status": "completed"}),
            ],
        ),
        reply("Listo."),
    ]

    events = send(chat, "Renómbrala, quítale la fecha y complétala")

    assert [e["action"]["status"] for e in of_type(events, "action")] == ["executed", "executed"]
    task = db.scalars(select(Task)).one()
    assert (task.title, task.due_at, task.status) == ("Comprar pan integral", None, "completed")
    # Both results go back to the model in a single message.
    results = tool_results(fake_claude.requests[1])
    assert [r["tool_use_id"] for r in results] == ["toolu_update_task_0", "toolu_set_task_status_1"]


def test_deleting_always_requires_confirmation(
    chat: TestClient, db: Session, fake_claude: FakeAnthropic
) -> None:
    set_mode(chat, "automatic")
    task_id = chat.post("/tasks", json={"title": "Comprar pan"}).json()["id"]
    fake_claude.script = [reply("", [("delete_task", {"task_id": task_id})]), reply("Confírmalo.")]

    events = send(chat, "Elimina comprar pan")

    interaction_id, action_id = pending_action(events)
    assert of_type(events, "action")[0]["action"]["summary"] == "Eliminar la tarea «Comprar pan»"
    assert len(db.scalars(select(Task)).all()) == 1

    chat.post(f"/chat/interactions/{interaction_id}/actions/{action_id}/confirm")
    assert db.scalars(select(Task)).all() == []


# --- Validation of the model output (RF13) ---------------------------------------


@pytest.mark.parametrize(
    ("tool", "tool_input"),
    [
        ("create_task", {"title": "   ", "description": None, "due_at": None}),
        ("create_task", {"title": "x" * 201, "description": None, "due_at": None}),
        ("create_task", {"title": "Zona", "description": None, "due_at": "2026-10-20T15:00:00"}),
        ("create_task", {"title": "Fecha rara", "description": None, "due_at": "mañana"}),
        ("create_task", {"title": "Extra", "description": None, "due_at": None, "owner": "bea"}),
        ("create_task", {"title": "Incompleta"}),
        ("create_task", "not an object"),
        ("set_task_status", {"task_id": MISSING_ID, "status": "completed"}),
        ("set_task_status", {"task_id": "not-a-uuid", "status": "completed"}),
        ("delete_task", {"task_id": MISSING_ID}),
        ("update_task", {"task_id": MISSING_ID, "title": "x", "description": None,
                         "due_at": None, "clear_due_date": False}),
        ("drop_database", {}),
    ],
)  # fmt: skip
def test_invalid_actions_are_rejected_in_every_mode(
    chat: TestClient, db: Session, fake_claude: FakeAnthropic, tool: str, tool_input: Any
) -> None:
    set_mode(chat, "automatic")
    fake_claude.script = [reply("", [(tool, tool_input)]), reply("No pude hacerlo.")]

    events = send(chat, "Haz algo")

    [event] = of_type(events, "action")
    assert event["action"]["status"] == "rejected"
    assert event["action"]["result"]
    [result] = tool_results(fake_claude.requests[1])
    assert result["is_error"] is True
    assert db.scalars(select(Task)).all() == []
    assert "ai.action_rejected" in audit_actions(db)
    assert db.scalars(select(Interaction)).one().actions[0]["status"] == "rejected"


def test_update_without_changes_is_rejected(chat: TestClient, fake_claude: FakeAnthropic) -> None:
    task_id = chat.post("/tasks", json={"title": "Comprar pan"}).json()["id"]
    nothing = {"task_id": task_id, "title": None, "description": None, "due_at": None,
               "clear_due_date": False}  # fmt: skip
    fake_claude.script = [reply("", [("update_task", nothing)]), reply("Nada que cambiar.")]

    events = send(chat, "Edita la tarea")

    assert of_type(events, "action")[0]["action"]["status"] == "rejected"


def test_model_cannot_touch_another_users_task(
    chat: TestClient, db: Session, fake_claude: FakeAnthropic
) -> None:
    bea = auth_service.register_user(db, **BEA)
    foreign = Task(user_id=bea.id, title="Tarea de Bea")
    db.add(foreign)
    db.commit()
    set_mode(chat, "automatic")
    fake_claude.script = [
        reply(
            "",
            [
                ("list_tasks", {"status": "all"}),
                ("set_task_status", {"task_id": str(foreign.id), "status": "completed"}),
            ],
        ),
        reply("No encontré esa tarea."),
    ]

    events = send(chat, "Completa la tarea de Bea")

    listed, rejected = tool_results(fake_claude.requests[1])
    assert json.loads(listed["content"]) == {"tasks": []}
    assert rejected["is_error"] is True
    assert of_type(events, "action")[0]["action"]["status"] == "rejected"
    db.refresh(foreign)
    assert foreign.status == "pending"


# --- Stop reasons and failures ---------------------------------------------------


def test_truncated_tool_call_is_never_executed(
    chat: TestClient, db: Session, fake_claude: FakeAnthropic
) -> None:
    set_mode(chat, "automatic")
    fake_claude.script = [reply("", [("create_task", NEW_TASK)], stop_reason="max_tokens")]

    events = send(chat, "Crea la tarea")

    assert of_type(events, "action") == []
    assert db.scalars(select(Task)).all() == []
    assert "incompleta" in reply_text(events)
    assert len(fake_claude.requests) == 1


def test_refusal_runs_no_tools(chat: TestClient, db: Session, fake_claude: FakeAnthropic) -> None:
    set_mode(chat, "automatic")
    fake_claude.script = [reply("", [("create_task", NEW_TASK)], stop_reason="refusal")]

    events = send(chat, "Algo")

    assert db.scalars(select(Task)).all() == []
    assert reply_text(events) == "No puedo ayudar con esa solicitud."
    assert events[-1]["type"] == "done"


def test_tool_loop_is_bounded(chat: TestClient, fake_claude: FakeAnthropic) -> None:
    fake_claude.script = [
        reply("", [("list_tasks", {"status": "all"})]) for _ in range(assistant.MAX_ITERATIONS)
    ]

    events = send(chat, "Repite sin parar")

    assert len(fake_claude.requests) == assistant.MAX_ITERATIONS
    assert "demasiados pasos" in reply_text(events)
    assert events[-1]["type"] == "done"


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (api_error(anthropic.AuthenticationError, 401), "invalid_key"),
        (api_error(anthropic.PermissionDeniedError, 403), "key_without_access"),
        (api_error(anthropic.RateLimitError, 429), "rate_limited"),
        (api_error(anthropic.BadRequestError, 400), "provider_rejected"),
        (api_error(anthropic.InternalServerError, 500), "provider_unavailable"),
        (connection_error(), "provider_unavailable"),
    ],
)
def test_provider_failures_are_reported(
    chat: TestClient, db: Session, fake_claude: FakeAnthropic, error: Exception, code: str
) -> None:
    fake_claude.script = [error]

    events = send(chat, "Hola")

    assert of_type(events, "error") == [{"type": "error", "code": code}]
    assert events[-1]["type"] == "done"
    assert db.scalars(select(Interaction)).one().status == "error"
    # The rest of the application keeps working.
    assert chat.get("/tasks").status_code == 200


def test_failed_turns_are_left_out_of_the_context(
    chat: TestClient, fake_claude: FakeAnthropic
) -> None:
    fake_claude.script = [connection_error(), reply("Hola")]

    send(chat, "Primera")
    send(chat, "Segunda")

    assert fake_claude.requests[1]["messages"] == [{"role": "user", "content": "Segunda"}]


def test_failure_after_an_executed_action_keeps_its_record(
    chat: TestClient, db: Session, fake_claude: FakeAnthropic
) -> None:
    set_mode(chat, "automatic")
    fake_claude.script = [reply("", [("create_task", NEW_TASK)]), connection_error()]

    events = send(chat, "Crea la tarea")

    assert of_type(events, "error") == [{"type": "error", "code": "provider_unavailable"}]
    assert db.scalars(select(Task)).one().title == "Preparar informe"
    assert db.scalars(select(Interaction)).one().actions[0]["status"] == "executed"
