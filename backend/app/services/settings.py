import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core import crypto
from app.integrations.llm import catalog, registry
from app.integrations.llm.catalog import AiProvider
from app.models.user_settings import ExecutionMode, UserSettings

# Columns holding each provider's encrypted key and its last four characters.
_KEY_COLUMNS: dict[AiProvider, tuple[str, str]] = {
    AiProvider.ANTHROPIC: ("ai_key_encrypted", "ai_key_last4"),
    AiProvider.GEMINI: ("gemini_key_encrypted", "gemini_key_last4"),
}


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


def get_ai_model(settings: UserSettings) -> str:
    return catalog.resolve_model(settings.ai_model)


def get_ai_provider(settings: UserSettings) -> AiProvider:
    return catalog.provider_of(get_ai_model(settings))


def key_last4(settings: UserSettings, provider: AiProvider) -> str | None:
    encrypted_column, last4_column = _KEY_COLUMNS[provider]
    if getattr(settings, encrypted_column) is None:
        return None
    return getattr(settings, last4_column)


def has_ai_key(settings: UserSettings, provider: AiProvider) -> bool:
    return getattr(settings, _KEY_COLUMNS[provider][0]) is not None


def get_ai_key(settings: UserSettings, provider: AiProvider) -> str | None:
    encrypted = getattr(settings, _KEY_COLUMNS[provider][0])
    if encrypted is None:
        return None
    try:
        return crypto.decrypt(encrypted)
    except crypto.DecryptionError:
        return None


def set_ai_model(db: Session, settings: UserSettings, model: str) -> UserSettings:
    """Change the assistant's model. With a key stored, the key must have access to it."""
    provider = catalog.provider_of(model)
    api_key = get_ai_key(settings, provider)
    if api_key is not None:
        registry.validate_api_key(provider, api_key, model)
    settings.ai_model = model
    db.commit()
    db.refresh(settings)
    return settings


def save_ai_key(
    db: Session, settings: UserSettings, provider: AiProvider, api_key: str
) -> UserSettings:
    """Validate the key with its provider and store it encrypted. Nothing is stored if it fails."""
    selected = get_ai_model(settings)
    model = (
        selected
        if catalog.provider_of(selected) == provider
        else catalog.DEFAULT_MODEL_BY_PROVIDER[provider]
    )
    registry.validate_api_key(provider, api_key, model)

    encrypted_column, last4_column = _KEY_COLUMNS[provider]
    setattr(settings, encrypted_column, crypto.encrypt(api_key))
    setattr(settings, last4_column, api_key[-4:])
    db.commit()
    db.refresh(settings)
    return settings


def remove_ai_key(db: Session, settings: UserSettings, provider: AiProvider) -> UserSettings:
    encrypted_column, last4_column = _KEY_COLUMNS[provider]
    setattr(settings, encrypted_column, None)
    setattr(settings, last4_column, None)
    db.commit()
    db.refresh(settings)
    return settings


def start_new_conversation(db: Session, settings: UserSettings) -> UserSettings:
    settings.conversation_started_at = datetime.now(UTC)
    db.commit()
    db.refresh(settings)
    return settings
