from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.integrations.anthropic import client as anthropic_client
from app.models.user_settings import UserSettings
from app.modules.audit import service as audit
from app.modules.audit.actions import AuditAction
from app.modules.auth.dependencies import CurrentUser
from app.schemas.settings import AiKeyUpdate, SettingsRead, SettingsUpdate
from app.services import settings as settings_service

router = APIRouter(prefix="/settings", tags=["settings"])

DbSession = Annotated[Session, Depends(get_db)]


def _read(settings: UserSettings) -> SettingsRead:
    return SettingsRead(
        execution_mode=settings.execution_mode,
        ai_key_configured=settings.ai_key_encrypted is not None,
        ai_key_last4=settings.ai_key_last4,
        ai_model=anthropic_client.MODEL,
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
    settings = settings_service.set_execution_mode(db, settings, payload.execution_mode)
    audit.record(
        db,
        AuditAction.SETTINGS_UPDATED,
        actor_id=user.id,
        detail={"execution_mode": settings.execution_mode},
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
