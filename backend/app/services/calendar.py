import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.integrations.google import client as google
from app.models.connected_account import ConnectedAccount, ConnectionStatus, Provider
from app.services import connections


@dataclass
class CalendarEvent:
    id: str
    account_id: uuid.UUID
    account_email: str
    provider: str
    title: str
    start: str
    end: str
    all_day: bool
    location: str | None
    html_link: str | None


@dataclass
class AccountResult:
    account_id: uuid.UUID
    account_email: str
    provider: str
    status: str
    error: str | None = None


@dataclass
class CalendarResult:
    events: list[CalendarEvent] = field(default_factory=list)
    accounts: list[AccountResult] = field(default_factory=list)


def _to_event(raw: dict, account: ConnectedAccount) -> CalendarEvent | None:
    start, end = raw.get("start", {}), raw.get("end", {})
    all_day = "date" in start
    start_value = start.get("date") or start.get("dateTime")
    end_value = end.get("date") or end.get("dateTime")
    if raw.get("status") == "cancelled" or not start_value or not end_value:
        return None

    return CalendarEvent(
        id=raw["id"],
        account_id=account.id,
        account_email=account.account_email,
        provider=account.provider,
        title=raw.get("summary") or "(Sin título)",
        start=start_value,
        end=end_value,
        all_day=all_day,
        location=raw.get("location"),
        html_link=raw.get("htmlLink"),
    )


def _fetch_account_events(
    db: Session, account: ConnectedAccount, time_min: datetime, time_max: datetime
) -> list[dict]:
    access_token = connections.get_access_token(db, account)
    try:
        return google.list_events(access_token, time_min=time_min, time_max=time_max)
    except google.GoogleAuthError:
        # The token may have been invalidated before its expiry; try once with a fresh one.
        access_token = connections.refresh_account_token(db, account)
        try:
            return google.list_events(access_token, time_min=time_min, time_max=time_max)
        except google.GoogleAuthError as exc:
            account.status = ConnectionStatus.NEEDS_REAUTH.value
            db.commit()
            raise connections.ReauthorizationRequiredError from exc


def list_events(
    db: Session, *, user_id: uuid.UUID, time_min: datetime, time_max: datetime
) -> CalendarResult:
    """Read the events of every Google account the user has connected.

    A failing account does not prevent the others from being returned; its error is reported
    in the per-account results.
    """
    result = CalendarResult()
    for account in connections.list_user_accounts(db, user_id):
        if account.provider != Provider.GOOGLE.value:
            continue

        error: str | None = None
        try:
            raw_events = _fetch_account_events(db, account, time_min, time_max)
            result.events.extend(
                event for raw in raw_events if (event := _to_event(raw, account)) is not None
            )
        except connections.ReauthorizationRequiredError:
            error = "needs_reauth"
        except google.GoogleError:
            error = "provider_unavailable"

        result.accounts.append(
            AccountResult(
                account_id=account.id,
                account_email=account.account_email,
                provider=account.provider,
                status=account.status,
                error=error,
            )
        )

    result.events.sort(key=lambda event: (event.start[:10], not event.all_day, event.start))
    return result
