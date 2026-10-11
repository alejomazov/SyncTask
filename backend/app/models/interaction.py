import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class InteractionStatus(StrEnum):
    COMPLETED = "completed"
    ERROR = "error"


class ActionStatus(StrEnum):
    PENDING = "pending"
    EXECUTED = "executed"
    REJECTED = "rejected"
    DISCARDED = "discarded"
    FAILED = "failed"


class Interaction(Base):
    """One instruction given to the assistant, with its reply and the actions it proposed."""

    __tablename__ = "interactions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    instruction: Mapped[str] = mapped_column(Text)
    response: Mapped[str] = mapped_column(Text, default="")
    actions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    status: Mapped[str] = mapped_column(String(20), default=InteractionStatus.COMPLETED.value)
    # Set in Python (microsecond precision) so interactions keep a stable order.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )
