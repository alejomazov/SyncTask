import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.models.task import TaskStatus

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]


class TaskCreate(BaseModel):
    title: Title
    description: Description = ""
    due_at: datetime | None = None


class TaskUpdate(BaseModel):
    """Partial update: only the fields present in the request are changed."""

    title: Title | None = None
    description: Description | None = None
    due_at: datetime | None = None
    status: TaskStatus | None = None


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str
    due_at: datetime | None
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
