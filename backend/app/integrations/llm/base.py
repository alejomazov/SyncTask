"""Provider-neutral contract between the assistant and a language model."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

StopReason = Literal["end", "tool_use", "max_tokens", "refusal", "invalid_tool_call"]

ErrorCode = Literal[
    "invalid_key", "key_without_access", "rate_limited", "provider_rejected", "provider_unavailable"
]


class InvalidApiKeyError(Exception):
    """The provider rejected the key, or the key has no access to the model."""


class ProviderUnavailableError(Exception):
    """The provider could not be reached, so the key could not be checked."""


class ProviderError(Exception):
    """A request to the model failed; `code` says why in provider-neutral terms."""

    def __init__(self, code: ErrorCode) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    input: Any


@dataclass(frozen=True)
class ToolResult:
    call: ToolCall
    content: dict[str, Any]
    is_error: bool = False


@dataclass
class Turn:
    """What the model produced in one request."""

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop: StopReason = "end"


class ChatSession(Protocol):
    """One instruction being processed: the model is called until it stops using tools."""

    last_turn: Turn

    def stream_turn(self) -> Iterator[str]:
        """Call the model, yielding text as it is generated; then `last_turn` is set."""
        ...

    def add_tool_results(self, results: list[ToolResult]) -> None:
        """Give the model the results of the tool calls of the last turn."""
        ...
