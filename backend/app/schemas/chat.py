import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, StringConstraints


class ChatRequest(BaseModel):
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    # IANA time zone of the browser, e.g. "America/Santiago".
    timezone: str | None = None


class InteractionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    instruction: str
    response: str
    actions: list[dict[str, Any]]
    status: str
    created_at: datetime
