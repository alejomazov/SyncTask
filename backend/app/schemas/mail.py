import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MailMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    account_id: uuid.UUID
    account_email: str
    provider: str
    sender_name: str
    sender_email: str
    subject: str
    snippet: str
    received_at: datetime
    unread: bool
    html_link: str


class MailMessageDetail(MailMessageRead):
    recipients: str
    body: str
    # True when the text was cut because the message is very long.
    body_truncated: bool


class MailAccountResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    account_id: uuid.UUID
    account_email: str
    provider: str
    status: str
    error: str | None


class MailMessagesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    messages: list[MailMessageRead]
    accounts: list[MailAccountResult]
