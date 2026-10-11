import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ExecutionMode(StrEnum):
    CONFIRM = "confirm"
    AUTOMATIC = "automatic"


class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    execution_mode: Mapped[str] = mapped_column(String(20), default=ExecutionMode.CONFIRM.value)
    ai_key_encrypted: Mapped[str | None] = mapped_column(Text)
    # Shown in the UI so the user can recognise which key is stored.
    ai_key_last4: Mapped[str | None] = mapped_column(String(4))
    # Interactions before this instant are history only; they are not sent to the model.
    conversation_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
