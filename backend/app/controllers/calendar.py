from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import CurrentUser
from app.schemas.calendar import CalendarEventsResponse
from app.services import calendar
from app.services.connections import as_utc

router = APIRouter(prefix="/calendar", tags=["calendar"])

DbSession = Annotated[Session, Depends(get_db)]

DEFAULT_RANGE = timedelta(days=7)
MAX_RANGE = timedelta(days=62)


@router.get("/events", response_model=CalendarEventsResponse)
def list_events(
    db: DbSession,
    user: CurrentUser,
    time_min: Annotated[datetime | None, Query(alias="from")] = None,
    time_max: Annotated[datetime | None, Query(alias="to")] = None,
) -> calendar.CalendarResult:
    start = as_utc(time_min) if time_min else datetime.now(UTC)
    end = as_utc(time_max) if time_max else start + DEFAULT_RANGE
    if end <= start:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "'to' must be after 'from'")
    if end - start > MAX_RANGE:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Range cannot exceed {MAX_RANGE.days} days"
        )

    return calendar.list_events(db, user_id=user.id, time_min=start, time_max=end)
