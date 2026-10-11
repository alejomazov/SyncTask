"""Validation and execution of the actions proposed by the assistant."""

import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models.interaction import ActionStatus
from app.models.task import Task, TaskStatus
from app.modules.ai import tools
from app.modules.audit import service as audit
from app.modules.audit.actions import AuditAction
from app.services import calendar, tasks

_VIA = "assistant"


class ActionRejectedError(Exception):
    """The proposed action does not comply with the established formats."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def validate(db: Session, user_id: uuid.UUID, tool: str, raw_input: Any) -> tools._ToolInput:
    """Check a proposed action against its format before anything is executed (RF13)."""
    model = tools.INPUT_MODELS.get(tool)
    if model is None:
        raise ActionRejectedError(f"unknown action '{tool}'")
    if not isinstance(raw_input, dict):
        raise ActionRejectedError("the action input must be a JSON object")

    try:
        parsed = model.model_validate(raw_input)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or 'input'}: {error['msg']}"
            for error in exc.errors()
        )
        raise ActionRejectedError(problems) from exc

    task_id = getattr(parsed, "task_id", None)
    if task_id is not None and tasks.get_task(db, task_id=task_id, user_id=user_id) is None:
        raise ActionRejectedError("task_id does not match any task of the user")
    return parsed


def _format_datetime(value: datetime, timezone: ZoneInfo) -> str:
    return value.astimezone(timezone).strftime("%d-%m-%Y %H:%M")


def summarize(
    db: Session, user_id: uuid.UUID, tool: str, parsed: tools._ToolInput, timezone: ZoneInfo
) -> str:
    """Describe a validated action in the words shown to the user before confirming it."""
    task: Task | None = None
    task_id = getattr(parsed, "task_id", None)
    if task_id is not None:
        task = tasks.get_task(db, task_id=task_id, user_id=user_id)
    title = f"«{task.title}»" if task else ""

    if isinstance(parsed, tools.CreateTaskInput):
        due = (
            f", con fecha límite {_format_datetime(parsed.due_at, timezone)}"
            if parsed.due_at
            else ""
        )
        return f"Crear la tarea «{parsed.title}»{due}"
    if isinstance(parsed, tools.UpdateTaskInput):
        changes = []
        if parsed.title is not None:
            changes.append(f"título: «{parsed.title}»")
        if parsed.description is not None:
            changes.append("nueva descripción")
        if parsed.due_at is not None:
            changes.append(f"fecha límite: {_format_datetime(parsed.due_at, timezone)}")
        if parsed.clear_due_date:
            changes.append("sin fecha límite")
        return f"Editar la tarea {title} ({', '.join(changes)})"
    if isinstance(parsed, tools.SetTaskStatusInput):
        verb = "Completar" if parsed.status == TaskStatus.COMPLETED else "Reabrir"
        return f"{verb} la tarea {title}"
    if isinstance(parsed, tools.DeleteTaskInput):
        return f"Eliminar la tarea {title}"
    return tool


def _task_payload(task: Task) -> dict[str, Any]:
    return {
        "id": str(task.id),
        "title": task.title,
        "description": task.description,
        "due_at": task.due_at.isoformat() if task.due_at else None,
        "status": task.status,
    }


def _audit_task(
    db: Session, action: AuditAction, user_id: uuid.UUID, task: Task, ip_address: str | None
) -> None:
    audit.record(
        db,
        action,
        actor_id=user_id,
        target_type="task",
        target_id=task.id,
        detail={"title": task.title, "via": _VIA},
        ip_address=ip_address,
    )


def execute(
    db: Session,
    user_id: uuid.UUID,
    parsed: tools._ToolInput,
    *,
    ip_address: str | None = None,
) -> dict[str, Any]:
    """Run a validated action on behalf of the user and return its result."""
    if isinstance(parsed, tools.ListTasksInput):
        status = None if parsed.status == "all" else TaskStatus(parsed.status)
        found = tasks.list_tasks(db, user_id=user_id, status=status)
        return {"tasks": [_task_payload(task) for task in found]}

    if isinstance(parsed, tools.GetCalendarEventsInput):
        result = calendar.list_events(
            db, user_id=user_id, time_min=parsed.start, time_max=parsed.end
        )
        return {
            "events": [
                {
                    "title": event.title,
                    "start": event.start,
                    "end": event.end,
                    "all_day": event.all_day,
                    "location": event.location,
                    "account": event.account_email,
                }
                for event in result.events
            ],
            "accounts": [
                {"account": account.account_email, "error": account.error}
                for account in result.accounts
            ],
            "note": None if result.accounts else "The user has no connected calendar accounts.",
        }

    if isinstance(parsed, tools.CreateTaskInput):
        task = tasks.create_task(
            db,
            user_id=user_id,
            title=parsed.title,
            description=parsed.description or "",
            due_at=parsed.due_at,
        )
        _audit_task(db, AuditAction.TASK_CREATED, user_id, task, ip_address)
        return {"task": _task_payload(task)}

    task = tasks.get_task(db, task_id=parsed.task_id, user_id=user_id)  # type: ignore[attr-defined]
    if task is None:
        raise ActionRejectedError("task_id does not match any task of the user")

    if isinstance(parsed, tools.UpdateTaskInput):
        changes: dict[str, Any] = {
            field: value
            for field in ("title", "description", "due_at")
            if (value := getattr(parsed, field)) is not None
        }
        if parsed.clear_due_date:
            changes["due_at"] = None
        task = tasks.update_task(db, task, changes)
        _audit_task(db, AuditAction.TASK_UPDATED, user_id, task, ip_address)
        return {"task": _task_payload(task)}

    if isinstance(parsed, tools.SetTaskStatusInput):
        if task.status != parsed.status:
            task = tasks.update_task(db, task, {"status": TaskStatus(parsed.status)})
            action = (
                AuditAction.TASK_COMPLETED
                if task.status == TaskStatus.COMPLETED
                else AuditAction.TASK_REOPENED
            )
            _audit_task(db, action, user_id, task, ip_address)
        return {"task": _task_payload(task)}

    if isinstance(parsed, tools.DeleteTaskInput):
        payload = _task_payload(task)
        _audit_task(db, AuditAction.TASK_DELETED, user_id, task, ip_address)
        tasks.delete_task(db, task)
        return {"deleted_task": payload}

    raise ActionRejectedError("unsupported action")


def new_action_record(
    tool: str, action_input: Any, summary: str, status: ActionStatus, result: str | None = None
) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "tool": tool,
        "input": action_input,
        "summary": summary,
        "status": status.value,
        "result": result,
    }
