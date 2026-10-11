import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class UserStatusUpdate(BaseModel):
    is_active: bool


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_id: uuid.UUID | None
    actor_email: str | None
    action: str
    target_type: str | None
    target_id: str | None
    detail: dict[str, Any]
    ip_address: str | None
    created_at: datetime
