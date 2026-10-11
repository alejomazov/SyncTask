import json
import uuid
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, get_db
from app.models.interaction import ActionStatus, Interaction
from app.models.user import User
from app.modules.ai import actions, assistant
from app.modules.audit import service as audit
from app.modules.audit.actions import AuditAction
from app.modules.auth.dependencies import CurrentUser
from app.schemas.chat import ChatRequest, InteractionRead
from app.services import settings as settings_service

router = APIRouter(prefix="/chat", tags=["chat"])

DbSession = Annotated[Session, Depends(get_db)]
SessionFactory = Callable[[], AbstractContextManager[Session]]

HISTORY_PAGE_SIZE = 100


def get_session_factory() -> SessionFactory:
    # The reply is streamed after the endpoint returns, so the stream owns its own session.
    return SessionLocal


def _timezone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name) if name else ZoneInfo("UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _sse(event: dict[str, Any]) -> str:
    return f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("/messages")
def send_message(
    payload: ChatRequest,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    session_factory: Annotated[SessionFactory, Depends(get_session_factory)],
) -> StreamingResponse:
    """Send an instruction to the assistant; the reply is streamed as Server-Sent Events."""
    settings = settings_service.get_settings(db, user.id)
    api_key = settings_service.get_ai_key(settings, settings_service.get_ai_provider(settings))
    if api_key is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "No API key is configured for the selected model"
        )

    user_id = user.id
    timezone = _timezone(payload.timezone)
    ip_address = request.client.host if request.client else None

    def stream() -> Iterator[str]:
        with session_factory() as session:
            current_user = session.get(User, user_id)
            if current_user is None:
                return
            events = assistant.run_instruction(
                session,
                user=current_user,
                settings=settings_service.get_settings(session, user_id),
                api_key=api_key,
                instruction=payload.message,
                timezone=timezone,
                ip_address=ip_address,
            )
            for event in events:
                yield _sse(event)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/interactions", response_model=list[InteractionRead])
def list_interactions(
    db: DbSession, user: CurrentUser, scope: Literal["conversation", "all"] = "conversation"
) -> list[Interaction]:
    """Interactions of the current conversation, or the whole history (RF16), oldest first."""
    if scope == "conversation":
        return assistant.load_history(db, settings_service.get_settings(db, user.id))

    recent = db.scalars(
        select(Interaction)
        .where(Interaction.user_id == user.id)
        .order_by(Interaction.created_at.desc())
        .limit(HISTORY_PAGE_SIZE)
    ).all()
    return list(reversed(recent))


@router.post("/conversation/reset", status_code=status.HTTP_204_NO_CONTENT)
def reset_conversation(db: DbSession, user: CurrentUser) -> None:
    """Start a new conversation: earlier interactions stay in the history only."""
    settings_service.start_new_conversation(db, settings_service.get_settings(db, user.id))


def _resolve_action(
    db: Session, user_id: uuid.UUID, interaction_id: uuid.UUID, action_id: uuid.UUID
) -> tuple[Interaction, dict[str, Any]]:
    interaction = db.scalar(
        select(Interaction).where(Interaction.id == interaction_id, Interaction.user_id == user_id)
    )
    action = next(
        (a for a in (interaction.actions if interaction else []) if a["id"] == str(action_id)),
        None,
    )
    if interaction is None or action is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Action not found")
    if action["status"] != ActionStatus.PENDING.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "The action is no longer pending")
    return interaction, action


def _save_action(
    db: Session, interaction: Interaction, action: dict[str, Any], **changes: Any
) -> Interaction:
    # Assign a new list so the JSON column is detected as modified.
    interaction.actions = [
        {**item, **changes} if item["id"] == action["id"] else item for item in interaction.actions
    ]
    db.commit()
    db.refresh(interaction)
    return interaction


@router.post(
    "/interactions/{interaction_id}/actions/{action_id}/confirm", response_model=InteractionRead
)
def confirm_action(
    interaction_id: uuid.UUID,
    action_id: uuid.UUID,
    request: Request,
    db: DbSession,
    user: CurrentUser,
) -> Interaction:
    """Execute an action the assistant proposed, after validating it again."""
    interaction, action = _resolve_action(db, user.id, interaction_id, action_id)
    ip_address = request.client.host if request.client else None
    try:
        parsed = actions.validate(db, user.id, action["tool"], action["input"])
        actions.execute(db, user.id, parsed, ip_address=ip_address)
    except actions.ActionRejectedError as exc:
        return _save_action(
            db, interaction, action, status=ActionStatus.FAILED.value, result=exc.reason
        )
    return _save_action(db, interaction, action, status=ActionStatus.EXECUTED.value)


@router.post(
    "/interactions/{interaction_id}/actions/{action_id}/discard", response_model=InteractionRead
)
def discard_action(
    interaction_id: uuid.UUID,
    action_id: uuid.UUID,
    request: Request,
    db: DbSession,
    user: CurrentUser,
) -> Interaction:
    """Discard a proposed action without changing anything."""
    interaction, action = _resolve_action(db, user.id, interaction_id, action_id)
    audit.record(
        db,
        AuditAction.AI_ACTION_DISCARDED,
        actor_id=user.id,
        detail={"tool": action["tool"], "summary": action["summary"]},
        ip_address=request.client.host if request.client else None,
    )
    return _save_action(db, interaction, action, status=ActionStatus.DISCARDED.value)
