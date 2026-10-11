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
    assert client.put("/settings/ai-key", json={"api_key": VALID_KEY}).status_code == 401
    assert client.delete("/settings/ai-key").status_code == 401


def test_default_settings(ana_client: TestClient) -> None:
    assert ana_client.get("/settings").json() == {
        "execution_mode": "confirm",
        "ai_key_configured": False,
        "ai_key_last4": None,
        "ai_model": "claude-opus-5-5",
    }


def test_update_execution_mode(ana_client: TestClient) -> None:
    response = ana_client.patch("/settings", json={"execution_mode": "automatic"})

    assert response.json()["execution_mode"] == "automatic"
    assert ana_client.get("/settings").json()["execution_mode"] == "automatic"
    assert ana_client.patch("/settings", json={"execution_mode": "yolo"}).status_code == 422


def test_save_ai_key_validates_and_encrypts(
    ana_client: TestClient, db: Session, fake_claude: FakeAnthropic
) -> None:
    response = ana_client.put("/settings/ai-key", json={"api_key": f"  {VALID_KEY}  "})

    assert response.status_code == 200
    assert response.json()["ai_key_configured"] is True
    assert response.json()["ai_key_last4"] == "1234"
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
    response = ana_client.put("/settings/ai-key", json={"api_key": INVALID_KEY})

    assert response.status_code == 422
    assert ana_client.get("/settings").json()["ai_key_configured"] is False
    assert "ai.key_saved" not in audit_actions(db)


def test_invalid_key_does_not_replace_a_valid_one(
    ana_client: TestClient, db: Session, fake_claude: FakeAnthropic
) -> None:
    ana_client.put("/settings/ai-key", json={"api_key": VALID_KEY})

    assert ana_client.put("/settings/ai-key", json={"api_key": INVALID_KEY}).status_code == 422

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

    assert ana_client.put("/settings/ai-key", json={"api_key": VALID_KEY}).status_code == 503
    assert ana_client.get("/settings").json()["ai_key_configured"] is False


def test_key_without_model_access_is_rejected(
    ana_client: TestClient, fake_claude: FakeAnthropic
) -> None:
    fake_claude.models_error = api_error(anthropic.PermissionDeniedError, 403)

    assert ana_client.put("/settings/ai-key", json={"api_key": VALID_KEY}).status_code == 422


def test_ai_key_format_is_checked_before_calling_anthropic(
    ana_client: TestClient, fake_claude: FakeAnthropic
) -> None:
    assert ana_client.put("/settings/ai-key", json={"api_key": "short"}).status_code == 422
    assert fake_claude.keys_used == []


def test_replace_and_remove_ai_key(
    ana_client: TestClient, db: Session, fake_claude: FakeAnthropic
) -> None:
    other_key = "sk-ant-valid-key-0000000000005678"
    fake_claude.valid_keys.add(other_key)
    ana_client.put("/settings/ai-key", json={"api_key": VALID_KEY})

    replaced = ana_client.put("/settings/ai-key", json={"api_key": other_key})
    assert replaced.json()["ai_key_last4"] == "5678"

    removed = ana_client.delete("/settings/ai-key")
    assert removed.json() == {
        "execution_mode": "confirm",
        "ai_key_configured": False,
        "ai_key_last4": None,
        "ai_model": "claude-opus-5-5",
    }
    assert db.scalars(select(UserSettings)).one().ai_key_encrypted is None
    assert "ai.key_removed" in audit_actions(db)


def test_settings_are_isolated_between_users(
    client: TestClient, ana: User, db: Session, fake_claude: FakeAnthropic
) -> None:
    login(client, ANA)
    client.put("/settings/ai-key", json={"api_key": VALID_KEY})
    client.patch("/settings", json={"execution_mode": "automatic"})

    auth_service.register_user(db, **BEA)
    login(client, BEA)

    assert client.get("/settings").json()["ai_key_configured"] is False
    assert client.get("/settings").json()["execution_mode"] == "confirm"
