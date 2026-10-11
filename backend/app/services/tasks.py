import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.task import Task, TaskStatus

# Fields a client may change; `due_at` is the only one that may be set to null.
_NULLABLE_FIELDS = {"due_at"}


def list_tasks(db: Session, *, user_id: uuid.UUID, status: TaskStatus | None = None) -> list[Task]:
    query = select(Task).where(Task.user_id == user_id)
    if status is not None:
        query = query.where(Task.status == status.value)
    # Pending first, then by due date (tasks without one last), newest first as tie-breaker.
    query = query.order_by(
        Task.status.desc(),
        Task.due_at.is_(None),
        Task.due_at,
        Task.created_at.desc(),
        Task.id,
    )
    return list(db.scalars(query))


def get_task(db: Session, *, task_id: uuid.UUID, user_id: uuid.UUID) -> Task | None:
    return db.scalar(select(Task).where(Task.id == task_id, Task.user_id == user_id))


def create_task(
    db: Session, *, user_id: uuid.UUID, title: str, description: str, due_at: datetime | None
) -> Task:
    task = Task(user_id=user_id, title=title, description=description, due_at=due_at)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def update_task(db: Session, task: Task, changes: dict[str, Any]) -> Task:
    for field, value in changes.items():
        if value is None and field not in _NULLABLE_FIELDS:
            continue
        setattr(task, field, value.value if isinstance(value, TaskStatus) else value)
    db.commit()
    db.refresh(task)
    return task


def delete_task(db: Session, task: Task) -> None:
    db.delete(task)
    db.commit()
