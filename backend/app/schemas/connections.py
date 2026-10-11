import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuthorizationUrl(BaseModel):
    authorization_url: str


class ConnectedAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: str
    account_email: str
    status: str
    # False for accounts connected before the mail permission existed, or without granting it.
    mail_enabled: bool
    created_at: datetime


class AdminConnectionRead(ConnectedAccountRead):
    user_id: uuid.UUID
    user_email: str
    user_full_name: str
    token_expires_at: datetime
    updated_at: datetime
