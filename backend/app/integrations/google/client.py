"""Thin HTTP client for Google OAuth 2.0 and the Google Calendar API."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"

CALENDAR_READONLY_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
SCOPES = ["openid", "email", CALENDAR_READONLY_SCOPE]

_TIMEOUT_SECONDS = 10
_MAX_EVENT_PAGES = 5

# Replaced in tests to avoid real network calls.
_transport: httpx.BaseTransport | None = None


class GoogleError(Exception):
    """Google could not be reached or returned an unexpected response."""


class GoogleAuthError(GoogleError):
    """Google rejected the credentials; the user has to authorize again."""


@dataclass(frozen=True)
class TokenResponse:
    access_token: str
    expires_in: int
    scope: str
    refresh_token: str | None


def _client() -> httpx.Client:
    return httpx.Client(transport=_transport, timeout=_TIMEOUT_SECONDS)


def _request(method: str, url: str, **kwargs: Any) -> httpx.Response:
    try:
        with _client() as client:
            return client.request(method, url, **kwargs)
    except httpx.HTTPError as exc:
        raise GoogleError(f"Google request failed: {type(exc).__name__}") from exc


def build_authorization_url(state: str) -> str:
    settings = get_settings()
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def _token_request(data: dict[str, str]) -> TokenResponse:
    settings = get_settings()
    response = _request(
        "POST",
        TOKEN_URL,
        data={
            **data,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
        },
    )
    if response.status_code in (400, 401):
        raise GoogleAuthError("Google rejected the authorization grant")
    if response.status_code != 200:
        raise GoogleError(f"Google token endpoint returned {response.status_code}")

    body = response.json()
    return TokenResponse(
        access_token=body["access_token"],
        expires_in=int(body.get("expires_in", 3600)),
        scope=body.get("scope", ""),
        refresh_token=body.get("refresh_token"),
    )


def exchange_code(code: str) -> TokenResponse:
    return _token_request(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": get_settings().google_redirect_uri,
        }
    )


def refresh_access_token(refresh_token: str) -> TokenResponse:
    return _token_request({"grant_type": "refresh_token", "refresh_token": refresh_token})


def revoke_token(token: str) -> bool:
    """Revoke a token at Google. Returns False if Google did not confirm the revocation."""
    try:
        return _request("POST", REVOKE_URL, data={"token": token}).status_code == 200
    except GoogleError:
        return False


def _authorized_get(url: str, access_token: str, params: dict[str, Any] | None = None) -> Any:
    response = _request(
        "GET", url, params=params, headers={"Authorization": f"Bearer {access_token}"}
    )
    if response.status_code == 401:
        raise GoogleAuthError("Google rejected the access token")
    if response.status_code != 200:
        raise GoogleError(f"Google API returned {response.status_code}")
    return response.json()


def get_account_email(access_token: str) -> str:
    email = _authorized_get(USERINFO_URL, access_token).get("email")
    if not email:
        raise GoogleError("Google did not return the account email")
    return email.lower()


def list_events(access_token: str, *, time_min: datetime, time_max: datetime) -> list[dict]:
    """Return the raw events of the primary calendar between the two instants."""
    params: dict[str, Any] = {
        "timeMin": time_min.isoformat(),
        "timeMax": time_max.isoformat(),
        "singleEvents": "true",
        "orderBy": "startTime",
        "maxResults": 250,
    }
    events: list[dict] = []
    for _ in range(_MAX_EVENT_PAGES):
        body = _authorized_get(EVENTS_URL, access_token, params)
        events.extend(body.get("items", []))
        page_token = body.get("nextPageToken")
        if not page_token:
            break
        params["pageToken"] = page_token
    return events
