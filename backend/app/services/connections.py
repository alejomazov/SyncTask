import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.config import get_settings
from app.integrations.google import client as google
from app.models.connected_account import ConnectedAccount, ConnectionStatus, Provider

_STATE_PURPOSE = "google_oauth"
_STATE_TTL = timedelta(minutes=10)
_EXPIRY_MARGIN = timedelta(seconds=60)


class AccountConnectionError(Exception):
    """The account could not be connected."""


class PermissionNotGrantedError(AccountConnectionError):
    """The user did not grant the calendar permission."""


class ReauthorizationRequiredError(Exception):
    """The stored credentials are no longer valid; the user has to connect again."""


def as_utc(value: datetime) -> datetime:
    # SQLite returns naive datetimes even for timezone-aware columns.
    return value if value.tzinfo else value.replace(tzinfo=UTC)


# --- OAuth state -----------------------------------------------------------------


def create_oauth_state(user_id: uuid.UUID) -> str:
    settings = get_settings()
    payload = {
        "sub": str(user_id),
        "purpose": _STATE_PURPOSE,
        "nonce": secrets.token_urlsafe(16),
        "exp": datetime.now(UTC) + _STATE_TTL,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def is_valid_oauth_state(state: str, user_id: uuid.UUID) -> bool:
    """True only if the state was issued by this server for this same user and has not expired."""
    settings = get_settings()
    try:
        payload = jwt.decode(state, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.InvalidTokenError:
        return False
    return payload.get("purpose") == _STATE_PURPOSE and payload.get("sub") == str(user_id)


# --- Connecting and disconnecting ------------------------------------------------


def connect_google_account(db: Session, *, user_id: uuid.UUID, code: str) -> ConnectedAccount:
    try:
        tokens = google.exchange_code(code)
        if google.CALENDAR_READONLY_SCOPE not in tokens.scope.split():
            google.revoke_token(tokens.access_token)
            raise PermissionNotGrantedError
        account_email = google.get_account_email(tokens.access_token)
    except google.GoogleError as exc:
        raise AccountConnectionError(str(exc)) from exc

    account = db.scalar(
        select(ConnectedAccount).where(
            ConnectedAccount.user_id == user_id,
            ConnectedAccount.provider == Provider.GOOGLE.value,
            ConnectedAccount.account_email == account_email,
        )
    )
    if account is None:
        if tokens.refresh_token is None:
            raise AccountConnectionError("Google did not return a refresh token")
        account = ConnectedAccount(
            user_id=user_id, provider=Provider.GOOGLE.value, account_email=account_email
        )
        db.add(account)

    _store_tokens(account, tokens)
    account.status = ConnectionStatus.ACTIVE.value
    db.commit()
    db.refresh(account)
    return account


def _store_tokens(account: ConnectedAccount, tokens: google.TokenResponse) -> None:
    account.access_token_encrypted = crypto.encrypt(tokens.access_token)
    if tokens.refresh_token:
        account.refresh_token_encrypted = crypto.encrypt(tokens.refresh_token)
    account.token_expires_at = datetime.now(UTC) + timedelta(seconds=tokens.expires_in)
    if tokens.scope:
        account.scopes = tokens.scope


def disconnect_account(db: Session, account: ConnectedAccount) -> bool:
    """Revoke the access at the provider and delete the stored tokens.

    Returns whether the provider confirmed the revocation; the tokens are deleted either way.
    """
    revoked = False
    try:
        token = crypto.decrypt(account.refresh_token_encrypted or account.access_token_encrypted)
        revoked = google.revoke_token(token)
    except crypto.DecryptionError:
        pass

    db.delete(account)
    db.commit()
    return revoked


# --- Queries ---------------------------------------------------------------------


def list_user_accounts(db: Session, user_id: uuid.UUID) -> list[ConnectedAccount]:
    return list(
        db.scalars(
            select(ConnectedAccount)
            .where(ConnectedAccount.user_id == user_id)
            .order_by(ConnectedAccount.created_at, ConnectedAccount.id)
        )
    )


def get_user_account(
    db: Session, *, account_id: uuid.UUID, user_id: uuid.UUID
) -> ConnectedAccount | None:
    return db.scalar(
        select(ConnectedAccount).where(
            ConnectedAccount.id == account_id, ConnectedAccount.user_id == user_id
        )
    )


def list_all_accounts(
    db: Session, *, page: int = 1, page_size: int = 20
) -> tuple[list[ConnectedAccount], int]:
    total = db.scalar(select(func.count()).select_from(ConnectedAccount)) or 0
    items = db.scalars(
        select(ConnectedAccount)
        .order_by(ConnectedAccount.created_at.desc(), ConnectedAccount.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(items), total


# --- Access tokens ---------------------------------------------------------------


def _mark_needs_reauth(db: Session, account: ConnectedAccount) -> None:
    account.status = ConnectionStatus.NEEDS_REAUTH.value
    db.commit()


def refresh_account_token(db: Session, account: ConnectedAccount) -> str:
    """Obtain and store a new access token. Marks the account for reauthorization on failure."""
    try:
        if account.refresh_token_encrypted is None:
            raise google.GoogleAuthError("No refresh token stored")
        tokens = google.refresh_access_token(crypto.decrypt(account.refresh_token_encrypted))
    except (google.GoogleAuthError, crypto.DecryptionError) as exc:
        _mark_needs_reauth(db, account)
        raise ReauthorizationRequiredError from exc

    _store_tokens(account, tokens)
    account.status = ConnectionStatus.ACTIVE.value
    db.commit()
    return tokens.access_token


def get_access_token(db: Session, account: ConnectedAccount) -> str:
    """Return a usable access token, refreshing it first if it has expired."""
    if account.status == ConnectionStatus.NEEDS_REAUTH.value:
        raise ReauthorizationRequiredError
    if as_utc(account.token_expires_at) - _EXPIRY_MARGIN <= datetime.now(UTC):
        return refresh_account_token(db, account)
    try:
        return crypto.decrypt(account.access_token_encrypted)
    except crypto.DecryptionError as exc:
        _mark_needs_reauth(db, account)
        raise ReauthorizationRequiredError from exc
