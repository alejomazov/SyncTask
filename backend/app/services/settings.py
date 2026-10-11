import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core import crypto
from app.integrations.anthropic import client as anthropic_client
from app.models.user_settings import ExecutionMode, UserSettings


def get_settings(db: Session, user_id: uuid.UUID) -> UserSettings:
    """Return the user's settings, creating them with the defaults on first use."""
    settings = db.get(UserSettings, user_id)
    if settings is None:
        settings = UserSettings(user_id=user_id, execution_mode=ExecutionMode.CONFIRM.value)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def set_execution_mode(db: Session, settings: UserSettings, mode: ExecutionMode) -> UserSettings:
    settings.execution_mode = mode.value
    db.commit()
    db.refresh(settings)
    return settings


def save_ai_key(db: Session, settings: UserSettings, api_key: str) -> UserSettings:
    """Validate the key with Anthropic and store it encrypted. Nothing is stored if it fails."""
    anthropic_client.validate_api_key(api_key)
    settings.ai_key_encrypted = crypto.encrypt(api_key)
    settings.ai_key_last4 = api_key[-4:]
    db.commit()
    db.refresh(settings)
    return settings


def remove_ai_key(db: Session, settings: UserSettings) -> UserSettings:
    settings.ai_key_encrypted = None
    settings.ai_key_last4 = None
    db.commit()
    db.refresh(settings)
    return settings


def get_ai_key(settings: UserSettings) -> str | None:
    if settings.ai_key_encrypted is None:
        return None
    try:
        return crypto.decrypt(settings.ai_key_encrypted)
    except crypto.DecryptionError:
        return None


def start_new_conversation(db: Session, settings: UserSettings) -> UserSettings:
    settings.conversation_started_at = datetime.now(UTC)
    db.commit()
    db.refresh(settings)
    return settings
