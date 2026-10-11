import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.user import User


class Provider(StrEnum):
    GOOGLE = "google"


class ConnectionStatus(StrEnum):
    ACTIVE = "active"
    NEEDS_REAUTH = "needs_reauth"


class ConnectedAccount(Base):
    __tablename__ = "connected_accounts"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", "account_email", name="uq_connected_account"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(20))
    account_email: Mapped[str] = mapped_column(String(320))
    access_token_encrypted: Mapped[str] = mapped_column(Text)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text)
    token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    scopes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default=ConnectionStatus.ACTIVE.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(lazy="joined")

    @property
    def user_email(self) -> str:
        return self.user.email

    @property
    def user_full_name(self) -> str:
        return self.user.full_name
