from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import crypto
from app.integrations.google import client as google
from app.models.audit_log import AuditLog
from app.models.connected_account import ConnectedAccount
from app.models.user import User, UserRole
from app.modules.auth import service as auth_service
from app.services import connections

ANA = {"email": "ana@example.com", "password": "supersecret1", "full_name": "Ana Soto"}
BEA = {"email": "bea@example.com", "password": "supersecret2", "full_name": "Bea Rojas"}
ADMIN = {"email": "admin@example.com", "password": "admin-secret-1", "full_name": "Admin"}
FULL_SCOPE = " ".join(google.SCOPES)


class FakeGoogle:
    """In-memory stand-in for Google's OAuth and Calendar endpoints."""

    def __init__(self) -> None:
        self.account_email = "ana.personal@gmail.com"
        self.granted_scope = FULL_SCOPE
        self.include_refresh_token = True
        self.reject_code = False
        self.reject_refresh = False
        self.reject_access_tokens: set[str] = set()
        self.events: list[dict] = []
        self.events_status = 200
        self.revoked: list[str] = []
        self.requests: list[httpx.Request] = []
        self._issued = 0

    def _new_access_token(self) -> str:
        self._issued += 1
        return f"access-{self._issued}"

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url).split("?")[0]
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}

        if url == google.TOKEN_URL:
            assert form["client_id"] == "test-client-id"
            assert form["client_secret"] == "test-client-secret"
            if form["grant_type"] == "authorization_code":
                if self.reject_code:
                    return httpx.Response(400, json={"error": "invalid_grant"})
                body = {
                    "access_token": self._new_access_token(),
                    "expires_in": 3600,
                    "scope": self.granted_scope,
                }
                if self.include_refresh_token:
                    body["refresh_token"] = "refresh-1"
                return httpx.Response(200, json=body)
            if self.reject_refresh:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(
                200,
                json={
                    "access_token": self._new_access_token(),
                    "expires_in": 3600,
                    "scope": self.granted_scope,
                },
            )

        if url == google.REVOKE_URL:
            self.revoked.append(form["token"])
            return httpx.Response(200)

        token = request.headers["Authorization"].removeprefix("Bearer ")
        if token in self.reject_access_tokens:
            return httpx.Response(401, json={"error": "invalid_token"})
        if url == google.USERINFO_URL:
            return httpx.Response(200, json={"email": self.account_email})
        if url == google.EVENTS_URL:
            if self.events_status != 200:
                return httpx.Response(self.events_status)
            return httpx.Response(200, json={"items": self.events})
        raise AssertionError(f"Unexpected request to {url}")

    def calls_to(self, url: str) -> list[httpx.Request]:
        return [r for r in self.requests if str(r.url).split("?")[0] == url]


@pytest.fixture
def fake_google(monkeypatch: pytest.MonkeyPatch) -> FakeGoogle:
    fake = FakeGoogle()
    monkeypatch.setattr(google, "_transport", httpx.MockTransport(fake.handler))
    return fake


@pytest.fixture
def ana(db: Session) -> User:
    return auth_service.register_user(db, **ANA)


@pytest.fixture
def ana_client(client: TestClient, ana: User) -> Generator[TestClient, None, None]:
    login(client, ANA)
    yield client


def login(client: TestClient, credentials: dict[str, str]) -> None:
    client.cookies.clear()
    response = client.post(
        "/auth/login", json={"email": credentials["email"], "password": credentials["password"]}
    )
    assert response.status_code == 200


def authorize(client: TestClient) -> str:
    """Start the flow and return the state Google would send back."""
    response = client.get("/integrations/google/authorize")
    assert response.status_code == 200
    return parse_qs(urlparse(response.json()["authorization_url"]).query)["state"][0]


def callback(client: TestClient, **params: str) -> str:
    response = client.get("/integrations/google/callback", params=params, follow_redirects=False)
    assert response.status_code == 303
    return response.headers["location"]


def connect(client: TestClient) -> None:
    location = callback(client, code="auth-code", state=authorize(client))
    assert location.endswith("/connections?google=connected")


def audit_actions(db: Session) -> list[str]:
    return list(db.scalars(select(AuditLog.action)))


# --- Authorization URL -----------------------------------------------------------


def test_authorize_requires_session(client: TestClient) -> None:
    assert client.get("/integrations/google/authorize").status_code == 401


def test_authorize_builds_read_only_consent_url(ana_client: TestClient) -> None:
    url = urlparse(ana_client.get("/integrations/google/authorize").json()["authorization_url"])
    params = {k: v[0] for k, v in parse_qs(url.query).items()}

    assert f"{url.scheme}://{url.netloc}{url.path}" == google.AUTH_URL
    assert params["client_id"] == "test-client-id"
    assert params["redirect_uri"] == "http://localhost:8000/integrations/google/callback"
    assert params["access_type"] == "offline"
    assert set(params["scope"].split()) == {"openid", "email", google.CALENDAR_READONLY_SCOPE}
    assert "client_secret" not in params


# --- Callback --------------------------------------------------------------------


def test_callback_stores_encrypted_tokens(
    ana_client: TestClient, ana: User, db: Session, fake_google: FakeGoogle
) -> None:
    connect(ana_client)

    account = db.scalars(select(ConnectedAccount)).one()
    assert account.user_id == ana.id
    assert account.provider == "google"
    assert account.account_email == "ana.personal@gmail.com"
    assert account.status == "active"
    assert "access-1" not in account.access_token_encrypted
    assert "refresh-1" not in (account.refresh_token_encrypted or "")
    assert crypto.decrypt(account.access_token_encrypted) == "access-1"
    assert crypto.decrypt(account.refresh_token_encrypted or "") == "refresh-1"
    assert audit_actions(db).count("connection.connected") == 1


def test_connections_list_never_exposes_tokens(
    ana_client: TestClient, fake_google: FakeGoogle
) -> None:
    connect(ana_client)

    response = ana_client.get("/connections")

    assert response.status_code == 200
    [item] = response.json()
    assert item["account_email"] == "ana.personal@gmail.com"
    assert item["status"] == "active"
    assert not any("token" in key for key in item)
    assert "access-1" not in response.text and "refresh-1" not in response.text


def test_callback_rejects_invalid_state(
    ana_client: TestClient, db: Session, fake_google: FakeGoogle
) -> None:
    location = callback(ana_client, code="auth-code", state="forged")

    assert location.endswith("google=error")
    assert db.scalars(select(ConnectedAccount)).all() == []
    assert fake_google.requests == []
    assert audit_actions(db).count("connection.failed") == 1


def test_callback_rejects_state_issued_to_another_user(
    client: TestClient, ana: User, db: Session, fake_google: FakeGoogle
) -> None:
    auth_service.register_user(db, **BEA)
    login(client, BEA)
    bea_state = authorize(client)

    login(client, ANA)
    location = callback(client, code="auth-code", state=bea_state)

    assert location.endswith("google=error")
    assert db.scalars(select(ConnectedAccount)).all() == []


def test_callback_without_session_stores_nothing(
    ana_client: TestClient, db: Session, fake_google: FakeGoogle
) -> None:
    state = authorize(ana_client)
    ana_client.cookies.clear()

    location = callback(ana_client, code="auth-code", state=state)

    assert location.endswith("google=session_expired")
    assert db.scalars(select(ConnectedAccount)).all() == []


def test_callback_when_user_denies_consent(
    ana_client: TestClient, db: Session, fake_google: FakeGoogle
) -> None:
    location = callback(ana_client, error="access_denied", state=authorize(ana_client))

    assert location.endswith("google=denied")
    assert db.scalars(select(ConnectedAccount)).all() == []
    assert fake_google.requests == []


def test_callback_when_calendar_permission_is_not_granted(
    ana_client: TestClient, db: Session, fake_google: FakeGoogle
) -> None:
    fake_google.granted_scope = "openid email"

    location = callback(ana_client, code="auth-code", state=authorize(ana_client))

    assert location.endswith("google=denied")
    assert db.scalars(select(ConnectedAccount)).all() == []
    assert fake_google.revoked == ["access-1"]


def test_callback_when_google_rejects_the_code(
    ana_client: TestClient, db: Session, fake_google: FakeGoogle
) -> None:
    fake_google.reject_code = True

    location = callback(ana_client, code="bad-code", state=authorize(ana_client))

    assert location.endswith("google=error")
    assert db.scalars(select(ConnectedAccount)).all() == []


def test_reconnecting_the_same_account_updates_it(
    ana_client: TestClient, db: Session, fake_google: FakeGoogle
) -> None:
    connect(ana_client)
    fake_google.include_refresh_token = False
    connect(ana_client)

    account = db.scalars(select(ConnectedAccount)).one()
    assert crypto.decrypt(account.access_token_encrypted) == "access-2"
    assert crypto.decrypt(account.refresh_token_encrypted or "") == "refresh-1"


def test_user_can_connect_several_google_accounts(
    ana_client: TestClient, fake_google: FakeGoogle
) -> None:
    connect(ana_client)
    fake_google.account_email = "ana.work@example.org"
    connect(ana_client)

    emails = [item["account_email"] for item in ana_client.get("/connections").json()]
    assert sorted(emails) == ["ana.personal@gmail.com", "ana.work@example.org"]


# --- Disconnecting ---------------------------------------------------------------


def test_disconnect_revokes_and_deletes_tokens(
    ana_client: TestClient, db: Session, fake_google: FakeGoogle
) -> None:
    connect(ana_client)
    account_id = ana_client.get("/connections").json()[0]["id"]

    assert ana_client.delete(f"/connections/{account_id}").status_code == 204

    assert fake_google.revoked == ["refresh-1"]
    assert db.scalars(select(ConnectedAccount)).all() == []
    assert ana_client.get("/connections").json() == []
    assert audit_actions(db).count("connection.disconnected") == 1


def test_user_cannot_disconnect_another_users_account(
    client: TestClient, ana: User, db: Session, fake_google: FakeGoogle
) -> None:
    login(client, ANA)
    connect(client)
    account_id = client.get("/connections").json()[0]["id"]

    auth_service.register_user(db, **BEA)
    login(client, BEA)

    assert client.get("/connections").json() == []
    assert client.delete(f"/connections/{account_id}").status_code == 404
    assert len(db.scalars(select(ConnectedAccount)).all()) == 1


# --- Calendar events -------------------------------------------------------------


def test_events_require_session(client: TestClient) -> None:
    assert client.get("/calendar/events").status_code == 401


def test_events_without_connected_accounts(ana_client: TestClient) -> None:
    assert ana_client.get("/calendar/events").json() == {"events": [], "accounts": []}


def test_events_are_read_from_google(ana_client: TestClient, fake_google: FakeGoogle) -> None:
    connect(ana_client)
    fake_google.events = [
        {
            "id": "evt-2",
            "summary": "Reunión de proyecto",
            "start": {"dateTime": "2026-10-12T15:00:00-03:00"},
            "end": {"dateTime": "2026-10-12T16:00:00-03:00"},
            "location": "Sala 2",
            "htmlLink": "https://calendar.google.com/event?eid=2",
        },
        {"id": "evt-1", "start": {"date": "2026-10-12"}, "end": {"date": "2026-10-13"}},
        {"id": "evt-3", "status": "cancelled", "start": {"date": "2026-10-12"}},
    ]

    body = ana_client.get(
        "/calendar/events",
        params={"from": "2026-10-12T00:00:00Z", "to": "2026-10-19T00:00:00Z"},
    ).json()

    assert [event["id"] for event in body["events"]] == ["evt-1", "evt-2"]
    all_day, meeting = body["events"]
    assert all_day["all_day"] is True and all_day["title"] == "(Sin título)"
    assert meeting["title"] == "Reunión de proyecto"
    assert meeting["start"] == "2026-10-12T15:00:00-03:00"
    assert meeting["account_email"] == "ana.personal@gmail.com"
    assert body["accounts"][0]["error"] is None

    [request] = fake_google.calls_to(google.EVENTS_URL)
    assert request.headers["Authorization"] == "Bearer access-1"
    assert request.url.params["timeMin"] == "2026-10-12T00:00:00+00:00"
    assert request.url.params["singleEvents"] == "true"


def test_events_reject_invalid_ranges(ana_client: TestClient) -> None:
    backwards = {"from": "2026-10-12T00:00:00Z", "to": "2026-10-11T00:00:00Z"}
    too_long = {"from": "2026-01-01T00:00:00Z", "to": "2026-12-31T00:00:00Z"}

    assert ana_client.get("/calendar/events", params=backwards).status_code == 422
    assert ana_client.get("/calendar/events", params=too_long).status_code == 422


def test_expired_access_token_is_refreshed(
    ana_client: TestClient, db: Session, fake_google: FakeGoogle
) -> None:
    connect(ana_client)
    account = db.scalars(select(ConnectedAccount)).one()
    account.token_expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()

    body = ana_client.get("/calendar/events").json()

    assert body["accounts"][0]["error"] is None
    [request] = fake_google.calls_to(google.EVENTS_URL)
    assert request.headers["Authorization"] == "Bearer access-2"
    db.refresh(account)
    assert crypto.decrypt(account.access_token_encrypted) == "access-2"
    assert connections.as_utc(account.token_expires_at) > datetime.now(UTC)


def test_token_invalidated_early_is_refreshed_once(
    ana_client: TestClient, fake_google: FakeGoogle
) -> None:
    connect(ana_client)
    fake_google.reject_access_tokens = {"access-1"}

    body = ana_client.get("/calendar/events").json()

    assert body["accounts"][0]["error"] is None
    assert len(fake_google.calls_to(google.EVENTS_URL)) == 2


def test_revoked_grant_marks_account_for_reauthorization(
    ana_client: TestClient, db: Session, fake_google: FakeGoogle
) -> None:
    connect(ana_client)
    account = db.scalars(select(ConnectedAccount)).one()
    account.token_expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()
    fake_google.reject_refresh = True

    body = ana_client.get("/calendar/events").json()

    assert body["events"] == []
    assert body["accounts"][0]["error"] == "needs_reauth"
    assert body["accounts"][0]["status"] == "needs_reauth"
    assert ana_client.get("/connections").json()[0]["status"] == "needs_reauth"

    # A later request must not keep calling Google with dead credentials.
    calls_before = len(fake_google.requests)
    ana_client.get("/calendar/events")
    assert len(fake_google.requests) == calls_before

    # Connecting again restores the account.
    fake_google.reject_refresh = False
    connect(ana_client)
    assert ana_client.get("/connections").json()[0]["status"] == "active"


def test_google_outage_is_reported_without_breaking_the_account(
    ana_client: TestClient, fake_google: FakeGoogle
) -> None:
    connect(ana_client)
    fake_google.events_status = 503

    response = ana_client.get("/calendar/events")

    assert response.status_code == 200
    assert response.json()["accounts"][0]["error"] == "provider_unavailable"
    assert ana_client.get("/connections").json()[0]["status"] == "active"


def test_events_are_isolated_between_users(
    client: TestClient, ana: User, db: Session, fake_google: FakeGoogle
) -> None:
    login(client, ANA)
    connect(client)
    fake_google.events = [
        {"id": "private", "start": {"date": "2026-10-12"}, "end": {"date": "2026-10-13"}}
    ]

    auth_service.register_user(db, **BEA)
    login(client, BEA)

    assert client.get("/calendar/events").json() == {"events": [], "accounts": []}
    assert fake_google.calls_to(google.EVENTS_URL) == []


# --- Administration --------------------------------------------------------------


def test_admin_lists_connections_without_tokens(
    client: TestClient, ana: User, db: Session, fake_google: FakeGoogle
) -> None:
    login(client, ANA)
    connect(client)
    assert client.get("/admin/connections").status_code == 403

    auth_service.register_user(db, **ADMIN, role=UserRole.ADMIN)
    login(client, ADMIN)
    response = client.get("/admin/connections")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    [item] = body["items"]
    assert item["user_email"] == ANA["email"]
    assert item["account_email"] == "ana.personal@gmail.com"
    assert item["provider"] == "google"
    assert item["status"] == "active"
    assert not any("token" in key and key != "token_expires_at" for key in item)
    assert "access-1" not in response.text and "refresh-1" not in response.text
