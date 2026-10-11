from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.integrations.anthropic import client as anthropic_client
from app.models.user_settings import UserSettings
from app.modules.audit import service as audit
from app.modules.audit.actions import AuditAction
from app.modules.auth.dependencies import CurrentUser
from app.schemas.settings import AiKeyUpdate, AiModelOption, SettingsRead, SettingsUpdate
from app.services import settings as settings_service

router = APIRouter(prefix="/settings", tags=["settings"])

DbSession = Annotated[Session, Depends(get_db)]


def _read(settings: UserSettings) -> SettingsRead:
    return SettingsRead(
        execution_mode=settings.execution_mode,
        ai_key_configured=settings.ai_key_encrypted is not None,
        ai_key_last4=settings.ai_key_last4,
        ai_model=settings_service.get_ai_model(settings),
        available_models=[
            AiModelOption(id=model_id, name=name)
            for model_id, name in anthropic_client.AVAILABLE_MODELS.items()
        ],
    )


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.get("", response_model=SettingsRead)
def get_settings(db: DbSession, user: CurrentUser) -> SettingsRead:
    return _read(settings_service.get_settings(db, user.id))


@router.patch("", response_model=SettingsRead)
def update_settings(
    payload: SettingsUpdate, request: Request, db: DbSession, user: CurrentUser
) -> SettingsRead:
    settings = settings_service.get_settings(db, user.id)
    changes: dict[str, str] = {}

    if payload.ai_model is not None and payload.ai_model != settings.ai_model:
        try:
            settings = settings_service.set_ai_model(db, settings, payload.ai_model)
        except anthropic_client.InvalidApiKeyError:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "The stored API key has no access to this model",
            ) from None
        except anthropic_client.ProviderUnavailableError:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "The model could not be verified right now"
            ) from None
        changes["ai_model"] = settings.ai_model

    if payload.execution_mode is not None and payload.execution_mode != settings.execution_mode:
        settings = settings_service.set_execution_mode(db, settings, payload.execution_mode)
        changes["execution_mode"] = settings.execution_mode

    if changes:
        audit.record(
            db,
            AuditAction.SETTINGS_UPDATED,
            actor_id=user.id,
            detail=changes,
            ip_address=_ip(request),
        )
    return _read(settings)


@router.put("/ai-key", response_model=SettingsRead)
def save_ai_key(
    payload: AiKeyUpdate, request: Request, db: DbSession, user: CurrentUser
) -> SettingsRead:
    settings = settings_service.get_settings(db, user.id)
    try:
        settings = settings_service.save_ai_key(db, settings, payload.api_key)
    except anthropic_client.InvalidApiKeyError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "The API key was rejected by Anthropic"
        ) from None
    except anthropic_client.ProviderUnavailableError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "The API key could not be verified right now"
        ) from None

    audit.record(db, AuditAction.AI_KEY_SAVED, actor_id=user.id, ip_address=_ip(request))
    return _read(settings)


@router.delete("/ai-key", response_model=SettingsRead)
def remove_ai_key(request: Request, db: DbSession, user: CurrentUser) -> SettingsRead:
    settings = settings_service.get_settings(db, user.id)
    if settings.ai_key_encrypted is not None:
        settings = settings_service.remove_ai_key(db, settings)
        audit.record(db, AuditAction.AI_KEY_REMOVED, actor_id=user.id, ip_address=_ip(request))
    return _read(settings)
