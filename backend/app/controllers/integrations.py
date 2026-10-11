from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.integrations.google import client as google
from app.models.connected_account import Provider
from app.modules.audit import service as audit
from app.modules.audit.actions import AuditAction
from app.modules.auth.dependencies import CurrentUser, OptionalUser
from app.schemas.connections import AuthorizationUrl
from app.services import connections

router = APIRouter(prefix="/integrations", tags=["integrations"])

DbSession = Annotated[Session, Depends(get_db)]


def _frontend_redirect(result: str) -> RedirectResponse:
    url = f"{get_settings().frontend_url}/connections?google={result}"
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/google/authorize", response_model=AuthorizationUrl)
def google_authorize(user: CurrentUser) -> dict[str, str]:
    settings = get_settings()
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Google integration is not configured"
        )
    state = connections.create_oauth_state(user.id)
    return {"authorization_url": google.build_authorization_url(state)}


@router.get("/google/callback", include_in_schema=False)
def google_callback(
    request: Request,
    db: DbSession,
    user: OptionalUser,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Google redirects the browser here after the user answers the consent screen."""
    if user is None:
        return _frontend_redirect("session_expired")

    ip_address = request.client.host if request.client else None

    def fail(reason: str, result: str) -> RedirectResponse:
        audit.record(
            db,
            AuditAction.CONNECTION_FAILED,
            actor_id=user.id,
            detail={"provider": Provider.GOOGLE.value, "reason": reason},
            ip_address=ip_address,
        )
        return _frontend_redirect(result)

    if state is None or not connections.is_valid_oauth_state(state, user.id):
        return fail("invalid_state", "error")
    if error is not None or code is None:
        return fail("access_denied", "denied")

    try:
        account = connections.connect_google_account(db, user_id=user.id, code=code)
    except connections.PermissionNotGrantedError:
        return fail("permission_not_granted", "denied")
    except connections.AccountConnectionError:
        return fail("provider_error", "error")

    audit.record(
        db,
        AuditAction.CONNECTION_CONNECTED,
        actor_id=user.id,
        target_type="connected_account",
        target_id=account.id,
        detail={"provider": account.provider, "account_email": account.account_email},
        ip_address=ip_address,
    )
    return _frontend_redirect("connected")
