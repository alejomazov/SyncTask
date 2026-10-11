import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.connected_account import ConnectedAccount
from app.modules.audit import service as audit
from app.modules.audit.actions import AuditAction
from app.modules.auth.dependencies import CurrentUser
from app.schemas.connections import ConnectedAccountRead
from app.services import connections

router = APIRouter(prefix="/connections", tags=["connections"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[ConnectedAccountRead])
def list_connections(db: DbSession, user: CurrentUser) -> list[ConnectedAccount]:
    return connections.list_user_accounts(db, user.id)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def disconnect(account_id: uuid.UUID, request: Request, db: DbSession, user: CurrentUser) -> None:
    account = connections.get_user_account(db, account_id=account_id, user_id=user.id)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connected account not found")

    detail = {"provider": account.provider, "account_email": account.account_email}
    revoked = connections.disconnect_account(db, account)

    audit.record(
        db,
        AuditAction.CONNECTION_DISCONNECTED,
        actor_id=user.id,
        target_type="connected_account",
        target_id=account_id,
        detail={**detail, "revoked_at_provider": revoked},
        ip_address=request.client.host if request.client else None,
    )
