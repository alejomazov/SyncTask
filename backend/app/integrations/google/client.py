"""Thin HTTP client for Google OAuth 2.0, the Google Calendar API and the Gmail API."""

import base64
import binascii
import logging
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
MESSAGES_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"

CALENDAR_READONLY_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
SCOPES = ["openid", "email", CALENDAR_READONLY_SCOPE, GMAIL_READONLY_SCOPE]

_TIMEOUT_SECONDS = 10
_MAX_EVENT_PAGES = 5
_MAX_BODY_CHARS = 15_000
_SUMMARY_HEADERS = ["From", "To", "Subject"]

logger = logging.getLogger(__name__)

# Replaced in tests to avoid real network calls.
_transport: httpx.BaseTransport | None = None


class GoogleError(Exception):
    """Google could not be reached or returned an unexpected response."""


class GoogleAuthError(GoogleError):
    """Google rejected the credentials; the user has to authorize again."""


class GoogleNotFoundError(GoogleError):
    """The requested resource does not exist in the account."""


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


def _get(
    client: httpx.Client, url: str, access_token: str, params: dict[str, Any] | None = None
) -> Any:
    try:
        response = client.get(
            url, params=params, headers={"Authorization": f"Bearer {access_token}"}
        )
    except httpx.HTTPError as exc:
        raise GoogleError(f"Google request failed: {type(exc).__name__}") from exc
    if response.status_code == 401:
        raise GoogleAuthError("Google rejected the access token")
    if response.status_code == 404:
        raise GoogleNotFoundError("Google did not find the resource")
    if response.status_code != 200:
        # Typically a 403: the API is not enabled in the Google Cloud project, or a quota.
        logger.warning("Google API returned %s for %s", response.status_code, url)
        raise GoogleError(f"Google API returned {response.status_code}")
    return response.json()


def _authorized_get(url: str, access_token: str, params: dict[str, Any] | None = None) -> Any:
    with _client() as client:
        return _get(client, url, access_token, params)


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


# --- Gmail -----------------------------------------------------------------------


@dataclass(frozen=True)
class GmailMessage:
    id: str
    thread_id: str
    sender: str
    recipients: str
    subject: str
    snippet: str
    received_at_ms: int
    unread: bool
    # Plain text of the message; only filled when the full message is requested.
    body: str | None = None
    body_truncated: bool = False


class _TextExtractor(HTMLParser):
    """Keeps the visible text of an HTML message."""

    _SKIPPED = {"script", "style", "head", "title"}
    _BREAKS = {"br", "p", "div", "tr", "li", "h1", "h2", "h3", "h4", "blockquote"}

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skipping = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIPPED:
            self._skipping += 1
        elif tag in self._BREAKS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIPPED and self._skipping:
            self._skipping -= 1

    def handle_data(self, data: str) -> None:
        if not self._skipping:
            self._parts.append(data)

    def text(self) -> str:
        lines = (" ".join(line.split()) for line in "".join(self._parts).splitlines())
        return "\n".join(line for line in lines if line)


def _decode_part(part: dict) -> str:
    data = part.get("body", {}).get("data")
    if not data:
        return ""
    try:
        return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")
    except (binascii.Error, ValueError):
        return ""


def _find_part(payload: dict, mime_type: str) -> dict | None:
    """First part of the given type, leaving attachments out."""
    if payload.get("mimeType") == mime_type and not payload.get("filename"):
        return payload
    for part in payload.get("parts", []):
        found = _find_part(part, mime_type)
        if found is not None:
            return found
    return None


def _body_text(payload: dict) -> str:
    plain = _find_part(payload, "text/plain")
    if plain is not None and (text := _decode_part(plain).strip()):
        return text
    html = _find_part(payload, "text/html")
    if html is None:
        return ""
    extractor = _TextExtractor()
    extractor.feed(_decode_part(html))
    return extractor.text()


def _to_message(raw: dict, *, with_body: bool) -> GmailMessage:
    payload = raw.get("payload", {})
    headers = {h.get("name", "").lower(): h.get("value", "") for h in payload.get("headers", [])}
    body: str | None = None
    truncated = False
    if with_body:
        full = _body_text(payload)
        truncated = len(full) > _MAX_BODY_CHARS
        body = full[:_MAX_BODY_CHARS]
    return GmailMessage(
        id=raw["id"],
        thread_id=raw.get("threadId", raw["id"]),
        sender=headers.get("from", ""),
        recipients=headers.get("to", ""),
        subject=headers.get("subject", ""),
        snippet=raw.get("snippet", ""),
        received_at_ms=int(raw.get("internalDate", 0)),
        unread="UNREAD" in raw.get("labelIds", []),
        body=body,
        body_truncated=truncated,
    )


def list_messages(
    access_token: str, *, max_results: int, unread_only: bool = False, query: str | None = None
) -> list[GmailMessage]:
    """Return the most recent messages of the inbox, newest first, without their bodies."""
    params: dict[str, Any] = {"labelIds": "INBOX", "maxResults": max_results}
    search = " ".join(part for part in ("is:unread" if unread_only else "", query or "") if part)
    if search:
        params["q"] = search
    with _client() as client:
        listing = _get(client, MESSAGES_URL, access_token, params)
        messages = []
        for item in listing.get("messages", []):
            try:
                raw = _get(
                    client,
                    f"{MESSAGES_URL}/{item['id']}",
                    access_token,
                    {"format": "metadata", "metadataHeaders": _SUMMARY_HEADERS},
                )
            except GoogleNotFoundError:
                # Deleted between the listing and the read.
                continue
            messages.append(_to_message(raw, with_body=False))
    return messages


def get_message(access_token: str, message_id: str) -> GmailMessage:
    """Return one message with its text. Attachments are not downloaded."""
    raw = _authorized_get(f"{MESSAGES_URL}/{message_id}", access_token, {"format": "full"})
    return _to_message(raw, with_body=True)
