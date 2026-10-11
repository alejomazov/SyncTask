from collections.abc import Generator

import anthropic
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import crypto
from app.integrations.anthropic import client as anthropic_client
from app.models.audit_log import AuditLog
from app.models.user import User
from app.models.user_settings import UserSettings
from app.modules.auth import service as auth_service
from tests.fake_anthropic import FakeAnthropic, api_error, connection_error

ANA = {"email": "ana@example.com", "password": "supersecret1", "full_name": "Ana Soto"}
BEA = {"email": "bea@example.com", "password": "supersecret2", "full_name": "Bea Rojas"}
VALID_KEY = "sk-ant-valid-key-0000000000001234"
INVALID_KEY = "sk-ant-invalid-key-000000000009999"
GEMINI_KEY = "AIzaSy-valid-gemini-key-00000000005678"
MODELS = [
    {"id": "claude-fable-5-1", "name": "Claude Fable 5.1", "provider": "anthropic"},
    {"id": "claude-opus-5-5", "name": "Claude Opus 5.5", "provider": "anthropic"},
    {"id": "claude-sonnet-5-5", "name": "Claude Sonnet 5.5", "provider": "anthropic"},
    {"id": "claude-haiku-5-5", "name": "Claude Haiku 5.5", "provider": "anthropic"},
    {"id": "gemini-3.1-pro-preview", "name": "Gemini 3.1 Pro (preview)", "provider": "gemini"},
    {"id": "gemini-3.8-flash", "name": "Gemini 3.8 Flash", "provider": "gemini"},
    {"id": "gemini-3.5-flash-lite", "name": "Gemini 3.5 Flash-Lite", "provider": "gemini"},
]


def provider_status(client: TestClient, provider: str) -> dict:
    providers = client.get("/settings").json()["providers"]
    return next(item for item in providers if item["id"] == provider)


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
def ana_client(client: TestClient, ana: User) -> Generator[TestClient, None, None]:
    login(client, ANA)
    yield client


def audit_actions(db: Session) -> list[str]:
    return sorted(db.scalars(select(AuditLog.action)))


def test_settings_require_session(client: TestClient) -> None:
    assert client.get("/settings").status_code == 401
    assert client.patch("/settings", json={"execution_mode": "automatic"}).status_code == 401
    assert client.put("/settings/ai-keys/anthropic", json={"api_key": VALID_KEY}).status_code == 401
    assert client.delete("/settings/ai-keys/anthropic").status_code == 401


def test_default_settings(ana_client: TestClient) -> None:
    assert ana_client.get("/settings").json() == {
        "execution_mode": "confirm",
        "ai_model": "claude-opus-5-5",
        "ai_provider": "anthropic",
        "custom_instructions": None,
        "custom_instructions_max_length": 2000,
        "assistant_ready": False,
        "providers": [
            {
                "id": "anthropic",
                "name": "Claude (Anthropic)",
                "key_configured": False,
                "key_last4": None,
            },
            {
                "id": "gemini",
                "name": "Gemini (Google)",
                "key_configured": False,
                "key_last4": None,
            },
        ],
        "available_models": MODELS,
    }


def test_update_execution_mode(ana_client: TestClient) -> None:
    response = ana_client.patch("/settings", json={"execution_mode": "automatic"})

    assert response.json()["execution_mode"] == "automatic"
    assert ana_client.get("/settings").json()["execution_mode"] == "automatic"
    assert ana_client.patch("/settings", json={"execution_mode": "yolo"}).status_code == 422


def test_choose_ai_model(ana_client: TestClient, db: Session, fake_claude: FakeAnthropic) -> None:
    response = ana_client.patch("/settings", json={"ai_model": "claude-sonnet-5-5"})

    assert response.status_code == 200
    assert response.json()["ai_model"] == "claude-sonnet-5-5"
    assert response.json()["execution_mode"] == "confirm"
    assert ana_client.get("/settings").json()["ai_model"] == "claude-sonnet-5-5"
    # Without a stored key there is nothing to check against Anthropic.
    assert fake_claude.models_checked == []
    updated = db.scalars(select(AuditLog).where(AuditLog.action == "settings.updated")).one()
    assert updated.detail == {"ai_model": "claude-sonnet-5-5"}


def test_unknown_ai_model_is_rejected(ana_client: TestClient) -> None:
    assert ana_client.patch("/settings", json={"ai_model": "gpt-4"}).status_code == 422
    assert ana_client.get("/settings").json()["ai_model"] == "claude-opus-5-5"


def test_key_is_validated_against_the_chosen_model(
    ana_client: TestClient, fake_claude: FakeAnthropic
) -> None:
    ana_client.patch("/settings", json={"ai_model": "claude-haiku-5-5"})

    ana_client.put("/settings/ai-keys/anthropic", json={"api_key": VALID_KEY})

    assert fake_claude.models_checked == ["claude-haiku-5-5"]


def test_changing_model_checks_the_stored_key_has_access(
    ana_client: TestClient, fake_claude: FakeAnthropic
) -> None:
    ana_client.put("/settings/ai-keys/anthropic", json={"api_key": VALID_KEY})

    assert ana_client.patch("/settings", json={"ai_model": "claude-sonnet-5-5"}).status_code == 200
    assert fake_claude.models_checked == ["claude-opus-5-5", "claude-sonnet-5-5"]

    fake_claude.models_error = api_error(anthropic.PermissionDeniedError, 403)
    denied = ana_client.patch("/settings", json={"ai_model": "claude-fable-5-1"})
    assert denied.status_code == 422
    assert ana_client.get("/settings").json()["ai_model"] == "claude-sonnet-5-5"

    fake_claude.models_error = connection_error()
    assert ana_client.patch("/settings", json={"ai_model": "claude-fable-5-1"}).status_code == 503
    assert ana_client.get("/settings").json()["ai_model"] == "claude-sonnet-5-5"


def test_retired_model_falls_back_to_the_default(ana_client: TestClient, db: Session) -> None:
    ana_client.get("/settings")
    stored = db.scalars(select(UserSettings)).one()
    stored.ai_model = "claude-retired-1"
    db.commit()

    assert ana_client.get("/settings").json()["ai_model"] == "claude-opus-5-5"


def test_save_ai_key_validates_and_encrypts(
    ana_client: TestClient, db: Session, fake_claude: FakeAnthropic
) -> None:
    response = ana_client.put("/settings/ai-keys/anthropic", json={"api_key": f"  {VALID_KEY}  "})

    assert response.status_code == 200
    assert response.json()["assistant_ready"] is True
    assert provider_status(ana_client, "anthropic") == {
        "id": "anthropic",
        "name": "Claude (Anthropic)",
        "key_configured": True,
        "key_last4": "1234",
    }
    assert VALID_KEY not in response.text
    assert VALID_KEY not in ana_client.get("/settings").text

    stored = db.scalars(select(UserSettings)).one()
    assert VALID_KEY not in (stored.ai_key_encrypted or "")
    assert crypto.decrypt(stored.ai_key_encrypted or "") == VALID_KEY
    assert fake_claude.keys_used == [VALID_KEY]
    assert "ai.key_saved" in audit_actions(db)
    assert VALID_KEY not in str(list(db.scalars(select(AuditLog.detail))))


def test_invalid_ai_key_is_not_stored(
    ana_client: TestClient, db: Session, fake_claude: FakeAnthropic
) -> None:
    response = ana_client.put("/settings/ai-keys/anthropic", json={"api_key": INVALID_KEY})

    assert response.status_code == 422
    assert provider_status(ana_client, "anthropic")["key_configured"] is False
    assert "ai.key_saved" not in audit_actions(db)


def test_invalid_key_does_not_replace_a_valid_one(
    ana_client: TestClient, db: Session, fake_claude: FakeAnthropic
) -> None:
    ana_client.put("/settings/ai-keys/anthropic", json={"api_key": VALID_KEY})

    assert (
        ana_client.put("/settings/ai-keys/anthropic", json={"api_key": INVALID_KEY}).status_code
        == 422
    )

    stored = db.scalars(select(UserSettings)).one()
    assert crypto.decrypt(stored.ai_key_encrypted or "") == VALID_KEY


@pytest.mark.parametrize(
    "error",
    [connection_error(), api_error(anthropic.InternalServerError, 500)],
)
def test_ai_key_is_not_stored_when_anthropic_is_unreachable(
    ana_client: TestClient, fake_claude: FakeAnthropic, error: Exception
) -> None:
    fake_claude.models_error = error

    assert (
        ana_client.put("/settings/ai-keys/anthropic", json={"api_key": VALID_KEY}).status_code
        == 503
    )
    assert provider_status(ana_client, "anthropic")["key_configured"] is False


def test_key_without_model_access_is_rejected(
    ana_client: TestClient, fake_claude: FakeAnthropic
) -> None:
    fake_claude.models_error = api_error(anthropic.PermissionDeniedError, 403)

    assert (
        ana_client.put("/settings/ai-keys/anthropic", json={"api_key": VALID_KEY}).status_code
        == 422
    )


def test_ai_key_format_is_checked_before_calling_anthropic(
    ana_client: TestClient, fake_claude: FakeAnthropic
) -> None:
    assert (
        ana_client.put("/settings/ai-keys/anthropic", json={"api_key": "short"}).status_code == 422
    )
    assert fake_claude.keys_used == []


def test_replace_and_remove_ai_key(
    ana_client: TestClient, db: Session, fake_claude: FakeAnthropic
) -> None:
    other_key = "sk-ant-valid-key-0000000000005678"
    fake_claude.valid_keys.add(other_key)
    ana_client.put("/settings/ai-keys/anthropic", json={"api_key": VALID_KEY})

    replaced = ana_client.put("/settings/ai-keys/anthropic", json={"api_key": other_key})
    assert replaced.status_code == 200
    assert provider_status(ana_client, "anthropic")["key_last4"] == "5678"

    removed = ana_client.delete("/settings/ai-keys/anthropic")
    assert removed.json()["assistant_ready"] is False
    assert provider_status(ana_client, "anthropic")["key_last4"] is None
    assert db.scalars(select(UserSettings)).one().ai_key_encrypted is None
    assert "ai.key_removed" in audit_actions(db)


def test_save_and_remove_custom_instructions(ana_client: TestClient, db: Session) -> None:
    text = "Resume mi agenda agrupada por día y trátame de tú."

    response = ana_client.patch("/settings", json={"custom_instructions": f"  {text}\n"})

    assert response.status_code == 200
    assert response.json()["custom_instructions"] == text
    assert ana_client.get("/settings").json()["custom_instructions"] == text

    # Updating another setting leaves the instructions untouched.
    ana_client.patch("/settings", json={"execution_mode": "automatic"})
    assert ana_client.get("/settings").json()["custom_instructions"] == text

    assert ana_client.patch("/settings", json={"custom_instructions": ""}).status_code == 200
    assert ana_client.get("/settings").json()["custom_instructions"] is None
    assert db.scalars(select(UserSettings)).one().custom_instructions is None


def test_custom_instructions_have_a_length_limit(ana_client: TestClient) -> None:
    assert (
        ana_client.patch("/settings", json={"custom_instructions": "a" * 2000}).status_code == 200
    )
    assert (
        ana_client.patch("/settings", json={"custom_instructions": "a" * 2001}).status_code == 422
    )
    assert len(ana_client.get("/settings").json()["custom_instructions"]) == 2000


def test_custom_instructions_text_is_kept_out_of_the_audit_trail(
    ana_client: TestClient, db: Session
) -> None:
    ana_client.patch("/settings", json={"custom_instructions": "Háblame de usted."})
    ana_client.patch("/settings", json={"custom_instructions": "Háblame de usted."})
    ana_client.patch("/settings", json={"custom_instructions": ""})

    logs = db.scalars(select(AuditLog).where(AuditLog.action == "settings.updated")).all()
    assert sorted(log.detail["custom_instructions"] for log in logs) == ["removed", "updated"]


def test_settings_are_isolated_between_users(
    client: TestClient, ana: User, db: Session, fake_claude: FakeAnthropic
) -> None:
    login(client, ANA)
    client.put("/settings/ai-keys/anthropic", json={"api_key": VALID_KEY})
    client.patch("/settings", json={"execution_mode": "automatic"})
    client.patch("/settings", json={"custom_instructions": "Responde en inglés."})

    auth_service.register_user(db, **BEA)
    login(client, BEA)

    assert client.get("/settings").json()["custom_instructions"] is None
    assert client.get("/settings").json()["assistant_ready"] is False
    assert client.get("/settings").json()["execution_mode"] == "confirm"
