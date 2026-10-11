import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.user import User
from app.modules.audit.actions import AuditAction


def record(
    db: Session,
    action: AuditAction,
    *,
    actor_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: uuid.UUID | str | None = None,
    detail: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_id=actor_id,
        action=action.value,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        detail=detail or {},
        ip_address=ip_address,
    )
    db.add(entry)
    db.commit()
    return entry


def list_logs(
    db: Session,
    *,
    action: str | None = None,
    actor_email: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[AuditLog], int]:
    query = select(AuditLog)
    if action:
        query = query.where(AuditLog.action == action)
    if actor_email:
        query = query.join(AuditLog.actor).where(User.email.ilike(f"%{actor_email.strip()}%"))
    if date_from:
        query = query.where(AuditLog.created_at >= date_from)
    if date_to:
        query = query.where(AuditLog.created_at <= date_to)

    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    items = db.scalars(
        query.order_by(AuditLog.created_at.desc(), AuditLog.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(items), total
