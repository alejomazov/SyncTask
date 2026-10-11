"""Actions the assistant may propose, and the formats they must comply with (RF13)."""

import uuid
from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, StringConstraints, model_validator

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]


class _ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ListTasksInput(_ToolInput):
    status: Literal["pending", "completed", "all"]


class GetCalendarEventsInput(_ToolInput):
    start: AwareDatetime
    end: AwareDatetime

    @model_validator(mode="after")
    def _check_range(self) -> "GetCalendarEventsInput":
        if self.end <= self.start:
            raise ValueError("end must be after start")
        if (self.end - self.start).days > 62:
            raise ValueError("the range cannot exceed 62 days")
        return self


class CreateTaskInput(_ToolInput):
    title: Title
    description: Description | None
    due_at: AwareDatetime | None


class UpdateTaskInput(_ToolInput):
    task_id: uuid.UUID
    title: Title | None
    description: Description | None
    due_at: AwareDatetime | None
    clear_due_date: bool

    @model_validator(mode="after")
    def _check_changes(self) -> "UpdateTaskInput":
        if self.clear_due_date and self.due_at is not None:
            raise ValueError("due_at and clear_due_date cannot be used together")
        if not self.clear_due_date and all(
            value is None for value in (self.title, self.description, self.due_at)
        ):
            raise ValueError("at least one field must change")
        return self


class SetTaskStatusInput(_ToolInput):
    task_id: uuid.UUID
    status: Literal["pending", "completed"]


class DeleteTaskInput(_ToolInput):
    task_id: uuid.UUID


INPUT_MODELS: dict[str, type[_ToolInput]] = {
    "list_tasks": ListTasksInput,
    "get_calendar_events": GetCalendarEventsInput,
    "create_task": CreateTaskInput,
    "update_task": UpdateTaskInput,
    "set_task_status": SetTaskStatusInput,
    "delete_task": DeleteTaskInput,
}

# Tools that only read data run immediately; the rest go through the execution mode (RF14).
READ_ONLY_TOOLS = frozenset({"list_tasks", "get_calendar_events"})
# Irreversible actions ask for confirmation even in automatic mode.
ALWAYS_CONFIRM_TOOLS = frozenset({"delete_task"})

_NULLABLE_STRING = {"anyOf": [{"type": "string"}, {"type": "null"}]}
_ISO_HINT = "ISO 8601 date-time with UTC offset, for example 2026-10-20T15:00:00-03:00."


def _tool(name: str, description: str, properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        },
    }


TOOLS: list[dict[str, Any]] = [
    _tool(
        "list_tasks",
        "List the user's tasks in the internal task manager, with their ids. Call it before "
        "editing, completing or deleting a task, to obtain its id.",
        {"status": {"type": "string", "enum": ["pending", "completed", "all"]}},
    ),
    _tool(
        "get_calendar_events",
        "Read the events of the user's connected Google calendars between two instants "
        "(at most 62 days apart). Read-only: events cannot be created or modified.",
        {
            "start": {"type": "string", "description": _ISO_HINT},
            "end": {"type": "string", "description": _ISO_HINT},
        },
    ),
    _tool(
        "create_task",
        "Create a task in the user's task manager.",
        {
            "title": {"type": "string", "description": "Short title, at most 200 characters."},
            "description": {**_NULLABLE_STRING, "description": "Optional details, or null."},
            "due_at": {
                **_NULLABLE_STRING,
                "description": f"Optional due date, or null. {_ISO_HINT}",
            },
        },
    ),
    _tool(
        "update_task",
        "Change the title, description or due date of an existing task. Pass null for the "
        "fields that do not change.",
        {
            "task_id": {"type": "string", "description": "Id of the task, from list_tasks."},
            "title": {**_NULLABLE_STRING, "description": "New title, or null to keep it."},
            "description": {
                **_NULLABLE_STRING,
                "description": "New description, or null to keep it.",
            },
            "due_at": {
                **_NULLABLE_STRING,
                "description": f"New due date, or null to keep it. {_ISO_HINT}",
            },
            "clear_due_date": {
                "type": "boolean",
                "description": "True to remove the due date; due_at must then be null.",
            },
        },
    ),
    _tool(
        "set_task_status",
        "Mark a task as completed, or reopen it as pending.",
        {
            "task_id": {"type": "string", "description": "Id of the task, from list_tasks."},
            "status": {"type": "string", "enum": ["pending", "completed"]},
        },
    ),
    _tool(
        "delete_task",
        "Permanently delete a task. Always requires the user's confirmation.",
        {"task_id": {"type": "string", "description": "Id of the task, from list_tasks."}},
    ),
]
