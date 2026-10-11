import contextlib
import json
from collections.abc import Generator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from google.genai import types
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.controllers.chat import get_session_factory
from app.core import crypto
from app.integrations.anthropic import client as anthropic_client
from app.integrations.gemini import client as gemini_client
from app.main import app
from app.models.audit_log import AuditLog
from app.models.interaction import Interaction
from app.models.task import Task
from app.models.user import User
from app.models.user_settings import UserSettings
from app.modules.auth import service as auth_service
from tests import fake_anthropic
from tests.fake_anthropic import FakeAnthropic
from tests.fake_gemini import (
    SIGNATURE,
    FakeGemini,
    api_error,
    blocked_prompt,
    invalid_key_error,
    reply,
)

ANA = {"email": "ana@example.com", "password": "supersecret1", "full_name": "Ana Soto"}
CLAUDE_KEY = "sk-ant-valid-key-0000000000001234"
GEMINI_KEY = "AIzaSy-valid-gemini-key-00000000005678"
BAD_KEY = "AIzaSy-invalid-gemini-key-000000000000"
GEMINI_MODEL = "gemini-3.8-flash"
NEW_TASK = {"title": "Preparar informe", "description": None, "due_at": None}


@pytest.fixture
def fake_gemini(monkeypatch: pytest.MonkeyPatch) -> FakeGemini:
    fake = FakeGemini()
    monkeypatch.setattr(gemini_client, "_client_factory", fake.for_key)
    return fake


@pytest.fixture
def fake_claude(monkeypatch: pytest.MonkeyPatch) -> FakeAnthropic:
    fake = FakeAnthropic()
    monkeypatch.setattr(anthropic_client, "_client_factory", fake.for_key)
    return fake


@pytest.fixture
def ana(db: Session) -> User:
    return auth_service.register_user(db, **ANA)


@pytest.fixture
def ana_client(
    client: TestClient, ana: User, db: Session, fake_gemini: FakeGemini, fake_claude: FakeAnthropic
) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_session_factory] = lambda: lambda: contextlib.nullcontext(db)
    response = client.post("/auth/login", json={"email": ANA["email"], "password": ANA["password"]})
    assert response.status_code == 200
    yield client


@pytest.fixture
def chat(ana_client: TestClient) -> TestClient:
    """Client logged in as Ana, with a Gemini key and a Gemini model selected."""
    assert (
        ana_client.put("/settings/ai-keys/gemini", json={"api_key": GEMINI_KEY}).status_code == 200
    )
    assert ana_client.patch("/settings", json={"ai_model": GEMINI_MODEL}).status_code == 200
    return ana_client


def send(client: TestClient, message: str = "Hola") -> list[dict[str, Any]]:
    response = client.post("/chat/messages", json={"message": message})
    assert response.status_code == 200
    return [
        json.loads(chunk.split("\n", 1)[1].removeprefix("data: "))
        for chunk in response.text.strip().split("\n\n")
    ]


def of_type(events: list[dict[str, Any]], event_type: str) -> list[dict[str, Any]]:
    return [event for event in events if event["type"] == event_type]


def reply_text(events: list[dict[str, Any]]) -> str:
    return "".join(event["delta"] for event in of_type(events, "text"))


def provider_status(client: TestClient, provider: str) -> dict:
    providers = client.get("/settings").json()["providers"]
    return next(item for item in providers if item["id"] == provider)


# --- Keys ------------------------------------------------------------------------


def test_save_gemini_key_validates_and_encrypts(
    ana_client: TestClient, db: Session, fake_gemini: FakeGemini, fake_claude: FakeAnthropic
) -> None:
    response = ana_client.put("/settings/ai-keys/gemini", json={"api_key": GEMINI_KEY})

    assert response.status_code == 200
    assert GEMINI_KEY not in response.text
    assert provider_status(ana_client, "gemini") == {
        "id": "gemini",
        "name": "Gemini (Google)",
        "key_configured": True,
        "key_last4": "5678",
    }
    assert provider_status(ana_client, "anthropic")["key_configured"] is False
    # Claude was the selected model, so the key is checked against Gemini's default.
    assert fake_gemini.models_checked == ["gemini-3.8-flash"]
    assert fake_claude.keys_used == []

    stored = db.scalars(select(UserSettings)).one()
    assert crypto.decrypt(stored.gemini_key_encrypted or "") == GEMINI_KEY
    assert stored.ai_key_encrypted is None
    saved = db.scalars(select(AuditLog).where(AuditLog.action == "ai.key_saved")).one()
    assert saved.detail == {"provider": "gemini", "ai_model": "gemini-3.8-flash"}


def test_first_key_selects_a_model_of_its_provider(ana_client: TestClient) -> None:
    ana_client.patch("/settings", json={"ai_model": "claude-haiku-5-5"})

    saved = ana_client.put("/settings/ai-keys/gemini", json={"api_key": GEMINI_KEY}).json()

    # Haiku could not be used without a Claude key, so the assistant moves to Gemini.
    assert saved["ai_model"] == "gemini-3.8-flash"
    assert saved["ai_provider"] == "gemini"
    assert saved["assistant_ready"] is True


def test_saving_a_second_key_keeps_the_selected_model(ana_client: TestClient) -> None:
    ana_client.put("/settings/ai-keys/anthropic", json={"api_key": CLAUDE_KEY})
    ana_client.patch("/settings", json={"ai_model": "claude-haiku-5-5"})

    saved = ana_client.put("/settings/ai-keys/gemini", json={"api_key": GEMINI_KEY}).json()

    assert saved["ai_model"] == "claude-haiku-5-5"
    assert saved["assistant_ready"] is True


def test_rejected_key_does_not_change_the_selected_model(
    ana_client: TestClient, fake_gemini: FakeGemini
) -> None:
    fake_gemini.models_error = invalid_key_error()

    ana_client.put("/settings/ai-keys/gemini", json={"api_key": GEMINI_KEY})

    assert ana_client.get("/settings").json()["ai_model"] == "claude-opus-5-5"


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (invalid_key_error(), 422),
        (api_error(403, "Permission denied"), 422),
        (api_error(404, "Model not found"), 422),
        (api_error(429, "Quota exceeded"), 503),
        (api_error(500, "Internal"), 503),
        (httpx.ConnectError("network down"), 503),
    ],
)
def test_gemini_key_is_not_stored_when_it_cannot_be_verified(
    ana_client: TestClient, fake_gemini: FakeGemini, error: Exception, status: int
) -> None:
    fake_gemini.models_error = error

    response = ana_client.put("/settings/ai-keys/gemini", json={"api_key": GEMINI_KEY})

    assert response.status_code == status
    assert provider_status(ana_client, "gemini")["key_configured"] is False


def test_unrecognised_gemini_key_is_rejected(ana_client: TestClient) -> None:
    assert ana_client.put("/settings/ai-keys/gemini", json={"api_key": BAD_KEY}).status_code == 422


def test_unknown_provider_is_rejected(ana_client: TestClient) -> None:
    response = ana_client.put("/settings/ai-keys/openai", json={"api_key": GEMINI_KEY})

    assert response.status_code == 422


def test_each_provider_keeps_its_own_key(ana_client: TestClient, db: Session) -> None:
    ana_client.put("/settings/ai-keys/anthropic", json={"api_key": CLAUDE_KEY})
    ana_client.put("/settings/ai-keys/gemini", json={"api_key": GEMINI_KEY})

    assert provider_status(ana_client, "anthropic")["key_last4"] == "1234"
    assert provider_status(ana_client, "gemini")["key_last4"] == "5678"

    ana_client.delete("/settings/ai-keys/gemini")

    stored = db.scalars(select(UserSettings)).one()
    assert stored.gemini_key_encrypted is None
    assert crypto.decrypt(stored.ai_key_encrypted or "") == CLAUDE_KEY
    assert provider_status(ana_client, "anthropic")["key_configured"] is True


# --- Choosing the model ----------------------------------------------------------


def test_assistant_is_ready_only_with_the_key_of_the_selected_provider(
    ana_client: TestClient, fake_gemini: FakeGemini
) -> None:
    ana_client.put("/settings/ai-keys/anthropic", json={"api_key": CLAUDE_KEY})
    assert ana_client.get("/settings").json()["assistant_ready"] is True

    switched = ana_client.patch("/settings", json={"ai_model": GEMINI_MODEL}).json()
    assert switched["ai_provider"] == "gemini"
    assert switched["assistant_ready"] is False
    assert ana_client.post("/chat/messages", json={"message": "Hola"}).status_code == 409
    assert fake_gemini.requests == []

    ana_client.put("/settings/ai-keys/gemini", json={"api_key": GEMINI_KEY})
    assert ana_client.get("/settings").json()["assistant_ready"] is True
    # With Gemini selected, its key is checked against the selected model.
    assert fake_gemini.models_checked == [GEMINI_MODEL]


def test_changing_to_a_gemini_model_checks_the_gemini_key(
    ana_client: TestClient, fake_gemini: FakeGemini
) -> None:
    ana_client.put("/settings/ai-keys/gemini", json={"api_key": GEMINI_KEY})
    fake_gemini.models_error = api_error(404, "Model not found")

    response = ana_client.patch("/settings", json={"ai_model": "gemini-3.1-pro-preview"})

    assert response.status_code == 422
    assert ana_client.get("/settings").json()["ai_model"] == "gemini-3.8-flash"


# --- Chat ------------------------------------------------------------------------


def test_reply_is_streamed_and_stored(
    chat: TestClient, db: Session, fake_gemini: FakeGemini, fake_claude: FakeAnthropic
) -> None:
    fake_gemini.script = [reply("Hola Ana, ¿en qué te ayudo?")]

    events = send(chat, "Hola")

    assert len(of_type(events, "text")) == 2
    assert reply_text(events) == "Hola Ana, ¿en qué te ayudo?"
    assert events[-1]["type"] == "done"
    interaction = db.scalars(select(Interaction)).one()
    assert interaction.response == "Hola Ana, ¿en qué te ayudo?"
    assert interaction.model == GEMINI_MODEL
    assert fake_gemini.keys_used[-1] == GEMINI_KEY
    assert fake_claude.requests == []


def test_request_sent_to_gemini(chat: TestClient, fake_gemini: FakeGemini) -> None:
    fake_gemini.script = [reply("Listo")]

    send(chat, "¿Qué tengo hoy?")

    [request] = fake_gemini.requests
    assert request["model"] == GEMINI_MODEL
    assert [(c.role, c.parts[0].text) for c in request["contents"]] == [("user", "¿Qué tengo hoy?")]
    config = request["config"]
    assert "Ana Soto" in config.system_instruction
    assert GEMINI_KEY not in config.system_instruction
    assert config.automatic_function_calling.disable is True
    declarations = config.tools[0].function_declarations
    assert [d.name for d in declarations] == [
        "list_tasks",
        "get_calendar_events",
        "list_emails",
        "get_email",
        "create_task",
        "update_task",
        "set_task_status",
        "delete_task",
    ]
    for declaration in declarations:
        schema = declaration.parameters_json_schema
        assert schema["type"] == "object"
        assert "additionalProperties" not in json.dumps(schema)
        assert schema["required"] == list(schema["properties"])


def test_custom_instructions_reach_gemini(chat: TestClient, fake_gemini: FakeGemini) -> None:
    fake_gemini.script = [reply("Listo")]
    chat.patch("/settings", json={"custom_instructions": "Lista las tareas por vencimiento."})

    send(chat, "¿Qué tengo pendiente?")

    system = fake_gemini.requests[0]["config"].system_instruction
    assert "<preferencias_del_usuario>\nLista las tareas por vencimiento.\n" in system


def test_read_tool_result_goes_back_with_the_thought_signature(
    chat: TestClient, fake_gemini: FakeGemini
) -> None:
    chat.post("/tasks", json={"title": "Comprar pan"})
    fake_gemini.script = [
        reply("Reviso tus tareas.", [("list_tasks", {"status": "pending"})]),
        reply("Tienes una tarea: Comprar pan."),
    ]

    events = send(chat, "¿Qué tareas tengo?")

    assert of_type(events, "status") == [{"type": "status", "tool": "list_tasks"}]
    assert reply_text(events) == "Reviso tus tareas.\n\nTienes una tarea: Comprar pan."

    contents = fake_gemini.requests[1]["contents"]
    assert [content.role for content in contents] == ["user", "model", "user"]
    call_part = next(part for part in contents[1].parts if part.function_call)
    assert call_part.function_call.name == "list_tasks"
    assert call_part.thought_signature == SIGNATURE
    [response_part] = contents[2].parts
    assert response_part.function_response.name == "list_tasks"
    assert response_part.function_response.id is None
    tasks = response_part.function_response.response["result"]["tasks"]
    assert [task["title"] for task in tasks] == ["Comprar pan"]


def test_function_call_ids_are_echoed_when_the_api_sends_them(
    chat: TestClient, fake_gemini: FakeGemini
) -> None:
    fake_gemini.script = [
        reply("", [("list_tasks", {"status": "all"})], call_ids=True),
        reply("Sin tareas."),
    ]

    send(chat, "¿Qué tareas tengo?")

    [response_part] = fake_gemini.requests[1]["contents"][2].parts
    assert response_part.function_response.id == "fc_0"


def test_confirm_mode_holds_the_action_and_confirming_executes_it(
    chat: TestClient, db: Session, fake_gemini: FakeGemini
) -> None:
    fake_gemini.script = [reply("", [("create_task", NEW_TASK)]), reply("Confírmala.")]

    events = send(chat, "Crea la tarea")

    [event] = of_type(events, "action")
    assert event["action"]["status"] == "pending"
    assert event["action"]["summary"] == "Crear la tarea «Preparar informe»"
    assert db.scalars(select(Task)).all() == []
    [response_part] = fake_gemini.requests[1]["contents"][2].parts
    assert response_part.function_response.response["result"]["status"] == "pending_confirmation"

    path = f"/chat/interactions/{event['interaction_id']}/actions/{event['action']['id']}"
    assert chat.post(f"{path}/confirm").json()["actions"][0]["status"] == "executed"
    assert db.scalars(select(Task)).one().title == "Preparar informe"


def test_automatic_mode_executes_several_calls(
    chat: TestClient, db: Session, fake_gemini: FakeGemini
) -> None:
    chat.patch("/settings", json={"execution_mode": "automatic"})
    second = {"title": "Enviar informe", "description": None, "due_at": "2026-10-20T15:00:00-03:00"}
    fake_gemini.script = [
        reply("", [("create_task", NEW_TASK), ("create_task", second)]),
        reply("Creé las dos tareas."),
    ]

    events = send(chat, "Crea dos tareas")

    assert [e["action"]["status"] for e in of_type(events, "action")] == ["executed", "executed"]
    assert sorted(db.scalars(select(Task.title))) == ["Enviar informe", "Preparar informe"]
    # Both results go back in a single user message.
    parts = fake_gemini.requests[1]["contents"][2].parts
    assert [part.function_response.response["result"]["status"] for part in parts] == [
        "executed",
        "executed",
    ]


def test_invalid_action_is_rejected(chat: TestClient, db: Session, fake_gemini: FakeGemini) -> None:
    chat.patch("/settings", json={"execution_mode": "automatic"})
    invalid = {"title": "   ", "description": None, "due_at": None}
    fake_gemini.script = [reply("", [("create_task", invalid)]), reply("No pude crearla.")]

    events = send(chat, "Crea una tarea sin título")

    assert of_type(events, "action")[0]["action"]["status"] == "rejected"
    assert db.scalars(select(Task)).all() == []
    [response_part] = fake_gemini.requests[1]["contents"][2].parts
    assert "error" in response_part.function_response.response
    assert "result" not in response_part.function_response.response


@pytest.mark.parametrize(
    ("finish_reason", "expected"),
    [
        (types.FinishReason.MAX_TOKENS, "incompleta"),
        (types.FinishReason.SAFETY, "No puedo ayudar"),
        (types.FinishReason.PROHIBITED_CONTENT, "No puedo ayudar"),
        (types.FinishReason.MALFORMED_FUNCTION_CALL, "acción válida"),
    ],
)
def test_abnormal_stops_run_no_tools(
    chat: TestClient,
    db: Session,
    fake_gemini: FakeGemini,
    finish_reason: types.FinishReason,
    expected: str,
) -> None:
    chat.patch("/settings", json={"execution_mode": "automatic"})
    fake_gemini.script = [reply("", [("create_task", NEW_TASK)], finish_reason=finish_reason)]

    events = send(chat, "Crea la tarea")

    assert db.scalars(select(Task)).all() == []
    assert of_type(events, "action") == []
    assert expected in reply_text(events)
    assert len(fake_gemini.requests) == 1


def test_blocked_prompt_is_reported_as_a_refusal(chat: TestClient, fake_gemini: FakeGemini) -> None:
    fake_gemini.script = [blocked_prompt()]

    events = send(chat, "Algo")

    assert reply_text(events) == "No puedo ayudar con esa solicitud."
    assert events[-1]["type"] == "done"


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (invalid_key_error(), "invalid_key"),
        (api_error(401, "Unauthenticated"), "invalid_key"),
        (api_error(403, "Permission denied"), "key_without_access"),
        (api_error(404, "Model not found"), "key_without_access"),
        (api_error(429, "Quota exceeded"), "rate_limited"),
        (api_error(400, "Invalid request"), "provider_rejected"),
        (api_error(503, "Overloaded"), "provider_unavailable"),
        (httpx.ConnectError("network down"), "provider_unavailable"),
    ],
)
def test_provider_failures_are_reported(
    chat: TestClient, db: Session, fake_gemini: FakeGemini, error: Exception, code: str
) -> None:
    fake_gemini.script = [error]

    events = send(chat, "Hola")

    assert of_type(events, "error") == [{"type": "error", "code": code}]
    assert db.scalars(select(Interaction)).one().status == "error"
    assert chat.get("/tasks").status_code == 200


def test_conversation_continues_across_providers(
    chat: TestClient, fake_gemini: FakeGemini, fake_claude: FakeAnthropic
) -> None:
    chat.put("/settings/ai-keys/anthropic", json={"api_key": CLAUDE_KEY})
    chat.patch("/settings", json={"ai_model": "claude-opus-5-5"})
    fake_claude.script = [fake_anthropic.reply("Respuesta de Claude")]
    fake_gemini.script = [reply("Respuesta de Gemini")]

    send(chat, "Primera")
    chat.patch("/settings", json={"ai_model": GEMINI_MODEL})
    send(chat, "Segunda")

    contents = fake_gemini.requests[0]["contents"]
    assert [(content.role, content.parts[0].text) for content in contents] == [
        ("user", "Primera"),
        ("model", "Respuesta de Claude"),
        ("user", "Segunda"),
    ]
    history = chat.get("/chat/interactions", params={"scope": "all"}).json()
    assert [item["model"] for item in history] == ["claude-opus-5-5", GEMINI_MODEL]
