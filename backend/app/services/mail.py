import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parseaddr
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.integrations.google import client as google
from app.models.connected_account import ConnectedAccount, Provider
from app.services import connections


class MailAccountNotFoundError(Exception):
    """The account does not exist or belongs to another user."""


class MailPermissionMissingError(Exception):
    """The account was connected without the permission to read mail."""


class MailMessageNotFoundError(Exception):
    """The message does not exist in the account."""


@dataclass
class MailMessage:
    id: str
    account_id: uuid.UUID
    account_email: str
    provider: str
    sender_name: str
    sender_email: str
    recipients: str
    subject: str
    snippet: str
    received_at: datetime
    unread: bool
    html_link: str
    body: str | None = None
    body_truncated: bool = False


@dataclass
class AccountResult:
    account_id: uuid.UUID
    account_email: str
    provider: str
    status: str
    error: str | None = None


@dataclass
class MailResult:
    messages: list[MailMessage] = field(default_factory=list)
    accounts: list[AccountResult] = field(default_factory=list)


def _to_message(raw: google.GmailMessage, account: ConnectedAccount) -> MailMessage:
    name, address = parseaddr(raw.sender)
    return MailMessage(
        id=raw.id,
        account_id=account.id,
        account_email=account.account_email,
        provider=account.provider,
        sender_name=name or address or raw.sender,
        sender_email=address,
        recipients=raw.recipients,
        subject=raw.subject or "(Sin asunto)",
        snippet=raw.snippet,
        received_at=datetime.fromtimestamp(raw.received_at_ms / 1000, UTC),
        unread=raw.unread,
        html_link=(
            f"https://mail.google.com/mail/?authuser={quote(account.account_email)}"
            f"#all/{raw.thread_id}"
        ),
        body=raw.body,
        body_truncated=raw.body_truncated,
    )


def list_messages(
    db: Session,
    *,
    user_id: uuid.UUID,
    limit: int,
    unread_only: bool = False,
    query: str | None = None,
) -> MailResult:
    """Read the most recent inbox messages of every Google account the user has connected.

    Messages are read on demand and never stored. A failing account does not prevent the
    others from being returned; its error is reported in the per-account results.
    """
    result = MailResult()
    for account in connections.list_user_accounts(db, user_id):
        if account.provider != Provider.GOOGLE.value:
            continue

        error: str | None = None
        if not account.mail_enabled:
            error = "missing_permission"
        else:
            try:
                found = connections.call_google(
                    db,
                    account,
                    lambda token: google.list_messages(
                        token, max_results=limit, unread_only=unread_only, query=query
                    ),
                )
                result.messages.extend(_to_message(raw, account) for raw in found)
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

    result.messages.sort(key=lambda message: message.received_at, reverse=True)
    del result.messages[limit:]
    return result


def get_message(
    db: Session, *, user_id: uuid.UUID, account_id: uuid.UUID, message_id: str
) -> MailMessage:
    """Read one message with its text.

    Raises `ReauthorizationRequiredError` or `GoogleError` when the account cannot be read.
    """
    account = connections.get_user_account(db, account_id=account_id, user_id=user_id)
    if account is None or account.provider != Provider.GOOGLE.value:
        raise MailAccountNotFoundError
    if not account.mail_enabled:
        raise MailPermissionMissingError
    try:
        raw = connections.call_google(
            db, account, lambda token: google.get_message(token, message_id)
        )
    except google.GoogleNotFoundError as exc:
        raise MailMessageNotFoundError from exc
    return _to_message(raw, account)
