"""Runs one instruction through Claude: propose actions, validate them, execute or hold them."""

import json
import uuid
from collections.abc import Iterator
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import anthropic
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.anthropic import client as anthropic_client
from app.models.interaction import ActionStatus, Interaction, InteractionStatus
from app.models.user import User
from app.models.user_settings import ExecutionMode, UserSettings
from app.modules.ai import actions, tools
from app.modules.audit import service as audit
from app.modules.audit.actions import AuditAction

MAX_TOKENS = 16000
MAX_ITERATIONS = 8
HISTORY_LIMIT = 20

_REFUSAL_NOTE = "No puedo ayudar con esa solicitud."
_TRUNCATED_NOTE = (
    "La respuesta quedó incompleta porque era demasiado larga. Intenta acotar la instrucción."
)
_ITERATION_NOTE = (
    "Detuve la ejecución porque la instrucción requería demasiados pasos. Intenta dividirla."
)

_PENDING_RESULT = {
    "status": "pending_confirmation",
    "message": (
        "The action was NOT executed. It is waiting for the user to confirm or discard it "
        "on a card shown in the chat. Do not repeat it and do not say it was done; tell the "
        "user it is waiting for their confirmation."
    ),
}

_STATUS_LABELS = {
    ActionStatus.PENDING.value: "pendiente de confirmación",
    ActionStatus.EXECUTED.value: "ejecutada",
    ActionStatus.REJECTED.value: "rechazada por formato inválido",
    ActionStatus.DISCARDED.value: "descartada por el usuario",
    ActionStatus.FAILED.value: "no se pudo ejecutar",
}

_WEEKDAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def _system_prompt(user: User, mode: str, now: datetime, history: list[Interaction]) -> str:
    mode_text = (
        "confirmar: las acciones que modifican datos quedan pendientes hasta que el usuario "
        "las confirme en una tarjeta del chat"
        if mode == ExecutionMode.CONFIRM.value
        else "automático: las acciones que modifican datos se ejecutan de inmediato, salvo "
        "eliminar tareas, que siempre requiere confirmación"
    )
    recent_actions = [
        f"- {action['summary']}: {_STATUS_LABELS.get(action['status'], action['status'])}"
        for interaction in history
        for action in interaction.actions
    ][-15:]
    actions_text = "\n".join(recent_actions) if recent_actions else "- (ninguna)"

    return f"""Eres el asistente de SyncTask, una aplicación de productividad personal. \
Ayudas a {user.full_name} a organizar su agenda y sus tareas mediante instrucciones en \
lenguaje natural.

Qué puedes hacer con las herramientas:
- Consultar, crear, editar, completar, reabrir y eliminar tareas del gestor de tareas interno.
- Consultar los eventos de los calendarios de Google que el usuario tenga conectados (solo lectura).

Qué no puedes hacer todavía: crear o modificar eventos del calendario, ni leer o enviar correos. \
Si te lo piden, dilo con claridad y ofrece una alternativa, como crear una tarea.

Reglas:
- Consulta los datos con las herramientas antes de responder sobre tareas o agenda; no los inventes.
- Para editar, completar o eliminar una tarea, obtén primero su id con list_tasks. Si la \
instrucción es ambigua (varias tareas podrían coincidir), pregunta en vez de adivinar.
- El resultado de cada herramienta indica si la acción se ejecutó o si quedó pendiente de \
confirmación. Nunca afirmes que una acción se realizó si el resultado no lo dice.
- Las fechas que entregues a las herramientas deben incluir la zona horaria del usuario.
- Responde en el idioma del usuario, de forma breve y directa, en texto simple.

Modo de ejecución del usuario: {mode_text}.

Fecha y hora actual del usuario: {_WEEKDAYS[now.weekday()]} {now.isoformat(timespec="minutes")} \
(zona horaria {now.tzinfo}).

Acciones propuestas anteriormente en esta conversación y su estado actual:
{actions_text}"""


def load_history(db: Session, settings: UserSettings) -> list[Interaction]:
    """Interactions of the current conversation, oldest first."""
    query = select(Interaction).where(Interaction.user_id == settings.user_id)
    if settings.conversation_started_at is not None:
        query = query.where(Interaction.created_at >= settings.conversation_started_at)
    recent = db.scalars(query.order_by(Interaction.created_at.desc()).limit(HISTORY_LIMIT)).all()
    return list(reversed(recent))


def _history_messages(history: list[Interaction]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for interaction in history:
        if not interaction.response:
            continue
        messages.append({"role": "user", "content": interaction.instruction})
        messages.append({"role": "assistant", "content": interaction.response})
    return messages


def _error_code(exc: Exception) -> str:
    if isinstance(exc, anthropic.AuthenticationError):
        return "invalid_key"
    if isinstance(exc, anthropic.PermissionDeniedError):
        return "key_without_access"
    if isinstance(exc, anthropic.RateLimitError):
        return "rate_limited"
    if isinstance(exc, anthropic.APIStatusError) and exc.status_code < 500:
        return "provider_rejected"
    return "provider_unavailable"


def _handle_tool_use(
    db: Session,
    user: User,
    mode: str,
    timezone: ZoneInfo,
    ip_address: str | None,
    block: Any,
    recorded: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Validate one proposed action and execute it or hold it.

    Returns the tool result for the model and, for actions that modify data, the record
    shown to the user.
    """

    def tool_result(content: Any, *, is_error: bool = False) -> dict[str, Any]:
        result = {
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": json.dumps(content, ensure_ascii=False),
        }
        if is_error:
            result["is_error"] = True
        return result

    try:
        parsed = actions.validate(db, user.id, block.name, block.input)
    except actions.ActionRejectedError as exc:
        record = actions.new_action_record(
            block.name,
            block.input if isinstance(block.input, dict) else {},
            "Acción propuesta con formato inválido",
            ActionStatus.REJECTED,
            exc.reason,
        )
        recorded.append(record)
        audit.record(
            db,
            AuditAction.AI_ACTION_REJECTED,
            actor_id=user.id,
            detail={"tool": block.name, "reason": exc.reason},
            ip_address=ip_address,
        )
        return tool_result(
            {"error": f"Invalid action, not executed: {exc.reason}"}, is_error=True
        ), record

    if block.name in tools.READ_ONLY_TOOLS:
        return tool_result(actions.execute(db, user.id, parsed, ip_address=ip_address)), None

    summary = actions.summarize(db, user.id, block.name, parsed, timezone)
    action_input = parsed.model_dump(mode="json")
    needs_confirmation = (
        mode == ExecutionMode.CONFIRM.value or block.name in tools.ALWAYS_CONFIRM_TOOLS
    )
    if needs_confirmation:
        record = actions.new_action_record(block.name, action_input, summary, ActionStatus.PENDING)
        recorded.append(record)
        audit.record(
            db,
            AuditAction.AI_ACTION_PROPOSED,
            actor_id=user.id,
            detail={"tool": block.name, "summary": summary},
            ip_address=ip_address,
        )
        return tool_result(_PENDING_RESULT), record

    result = actions.execute(db, user.id, parsed, ip_address=ip_address)
    record = actions.new_action_record(block.name, action_input, summary, ActionStatus.EXECUTED)
    recorded.append(record)
    return tool_result({"status": "executed", **result}), record


def run_instruction(
    db: Session,
    *,
    user: User,
    settings: UserSettings,
    api_key: str,
    instruction: str,
    timezone: ZoneInfo,
    ip_address: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Process an instruction, yielding events for the chat as they happen.

    Events: `text` (reply fragments), `status` (a read-only tool is running), `action`
    (an action was executed, held for confirmation or rejected), `error`, and a final
    `done` carrying the id of the stored interaction.
    """
    history = load_history(db, settings)
    mode = settings.execution_mode
    system = _system_prompt(user, mode, datetime.now(timezone), history)
    messages = [*_history_messages(history), {"role": "user", "content": instruction}]

    reply_parts: list[str] = []
    recorded: list[dict[str, Any]] = []
    status = InteractionStatus.COMPLETED
    interaction_id = uuid.uuid4()

    def note(text: str) -> Iterator[dict[str, Any]]:
        prefix = "\n\n" if reply_parts else ""
        reply_parts.append(text)
        yield {"type": "text", "delta": prefix + text}

    try:
        client = anthropic_client.create_client(api_key)
        for _ in range(MAX_ITERATIONS):
            started_text = False
            with client.messages.stream(
                model=anthropic_client.MODEL,
                max_tokens=MAX_TOKENS,
                system=system,
                tools=tools.TOOLS,
                messages=messages,
                thinking={"type": "adaptive"},
                output_config={"effort": "medium"},
            ) as stream:
                for event in stream:
                    if event.type == "text":
                        prefix = "\n\n" if reply_parts and not started_text else ""
                        started_text = True
                        yield {"type": "text", "delta": prefix + event.text}
                response = stream.get_final_message()

            text = "".join(block.text for block in response.content if block.type == "text")
            if text:
                reply_parts.append(text)

            if response.stop_reason == "refusal":
                yield from note(_REFUSAL_NOTE)
                break

            tool_uses = [block for block in response.content if block.type == "tool_use"]
            if response.stop_reason == "max_tokens":
                # A truncated tool input can still parse as a valid object: never run it.
                yield from note(_TRUNCATED_NOTE)
                break
            if not tool_uses:
                break

            messages.append({"role": "assistant", "content": response.content})
            results = []
            for block in tool_uses:
                if block.name in tools.READ_ONLY_TOOLS:
                    yield {"type": "status", "tool": block.name}
                result, record = _handle_tool_use(
                    db, user, mode, timezone, ip_address, block, recorded
                )
                results.append(result)
                if record is not None:
                    yield {
                        "type": "action",
                        "interaction_id": str(interaction_id),
                        "action": record,
                    }
            messages.append({"role": "user", "content": results})
        else:
            yield from note(_ITERATION_NOTE)
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
        status = InteractionStatus.ERROR
        yield {"type": "error", "code": _error_code(exc)}
    finally:
        db.add(
            Interaction(
                id=interaction_id,
                user_id=user.id,
                instruction=instruction,
                response="\n\n".join(reply_parts),
                actions=recorded,
                status=status.value,
            )
        )
        db.commit()

    yield {"type": "done", "interaction_id": str(interaction_id)}
