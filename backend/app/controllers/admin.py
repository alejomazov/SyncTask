import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.modules.audit import service as audit
from app.modules.audit.actions import AuditAction
from app.modules.auth.dependencies import AdminUser, require_admin
from app.schemas.admin import AuditLogRead, UserStatusUpdate
from app.schemas.auth import UserRead
from app.schemas.common import Page
from app.services import users

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])

DbSession = Annotated[Session, Depends(get_db)]
PageNumber = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]


@router.get("/users", response_model=Page[UserRead])
def list_users(
    db: DbSession,
    search: str | None = None,
    page: PageNumber = 1,
    page_size: PageSize = 20,
) -> dict:
    items, total = users.list_users(db, search=search, page=page, page_size=page_size)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.patch("/users/{user_id}", response_model=UserRead)
def update_user_status(
    user_id: uuid.UUID,
    payload: UserStatusUpdate,
    request: Request,
    db: DbSession,
    admin: AdminUser,
) -> User:
    try:
        user = users.set_user_active(
            db, user_id=user_id, is_active=payload.is_active, acting_user_id=admin.id
        )
    except users.CannotDisableOwnAccountError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "You cannot disable your own account"
        ) from None
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    audit.record(
        db,
        AuditAction.ADMIN_USER_ENABLED if user.is_active else AuditAction.ADMIN_USER_DISABLED,
        actor_id=admin.id,
        target_type="user",
        target_id=user.id,
        detail={"email": user.email},
        ip_address=request.client.host if request.client else None,
    )
    return user


@router.get("/audit-logs", response_model=Page[AuditLogRead])
def list_audit_logs(
    db: DbSession,
    action: AuditAction | None = None,
    actor_email: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: PageNumber = 1,
    page_size: PageSize = 20,
) -> dict:
    items, total = audit.list_logs(
        db,
        action=action.value if action else None,
        actor_email=actor_email,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}
