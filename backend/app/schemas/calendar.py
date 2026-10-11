import uuid

from pydantic import BaseModel, ConfigDict


class CalendarEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    account_id: uuid.UUID
    account_email: str
    provider: str
    title: str
    # ISO date (all-day events) or ISO date-time with offset.
    start: str
    end: str
    all_day: bool
    location: str | None
    html_link: str | None


class CalendarAccountResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    account_id: uuid.UUID
    account_email: str
    provider: str
    status: str
    error: str | None


class CalendarEventsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    events: list[CalendarEventRead]
    accounts: list[CalendarAccountResult]
