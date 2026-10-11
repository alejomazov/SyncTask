import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.task import Task, TaskStatus
from app.modules.audit import service as audit
from app.modules.audit.actions import AuditAction
from app.modules.auth.dependencies import CurrentUser
from app.schemas.tasks import TaskCreate, TaskRead, TaskUpdate
from app.services import tasks

router = APIRouter(prefix="/tasks", tags=["tasks"])

DbSession = Annotated[Session, Depends(get_db)]


def _audit(
    db: Session, request: Request, action: AuditAction, *, user_id: uuid.UUID, task: Task
) -> None:
    audit.record(
        db,
        action,
        actor_id=user_id,
        target_type="task",
        target_id=task.id,
        detail={"title": task.title},
        ip_address=request.client.host if request.client else None,
    )


def _get_own_task(db: Session, task_id: uuid.UUID, user_id: uuid.UUID) -> Task:
    task = tasks.get_task(db, task_id=task_id, user_id=user_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    return task


@router.get("", response_model=list[TaskRead])
def list_tasks(
    db: DbSession, user: CurrentUser, task_status: TaskStatus | None = None
) -> list[Task]:
    return tasks.list_tasks(db, user_id=user.id, status=task_status)


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, request: Request, db: DbSession, user: CurrentUser) -> Task:
    task = tasks.create_task(
        db,
        user_id=user.id,
        title=payload.title,
        description=payload.description,
        due_at=payload.due_at,
    )
    _audit(db, request, AuditAction.TASK_CREATED, user_id=user.id, task=task)
    return task


@router.patch("/{task_id}", response_model=TaskRead)
def update_task(
    task_id: uuid.UUID, payload: TaskUpdate, request: Request, db: DbSession, user: CurrentUser
) -> Task:
    task = _get_own_task(db, task_id, user.id)
    previous_status = task.status
    changes = payload.model_dump(exclude_unset=True)
    task = tasks.update_task(db, task, changes)

    if task.status != previous_status:
        action = (
            AuditAction.TASK_COMPLETED
            if task.status == TaskStatus.COMPLETED
            else AuditAction.TASK_REOPENED
        )
        _audit(db, request, action, user_id=user.id, task=task)
    if changes.keys() - {"status"}:
        _audit(db, request, AuditAction.TASK_UPDATED, user_id=user.id, task=task)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: uuid.UUID, request: Request, db: DbSession, user: CurrentUser) -> None:
    task = _get_own_task(db, task_id, user.id)
    _audit(db, request, AuditAction.TASK_DELETED, user_id=user.id, task=task)
    tasks.delete_task(db, task)
