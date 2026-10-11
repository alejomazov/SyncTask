"""Claude, through the official Anthropic SDK and the key each user provides."""

import json
from collections.abc import Callable, Iterator
from typing import Any

import anthropic

from app.integrations.llm.base import (
    InvalidApiKeyError,
    ProviderError,
    ProviderUnavailableError,
    ToolCall,
    ToolResult,
    Turn,
)

MAX_TOKENS = 16000

# Replaced in tests to avoid real network calls.
_client_factory: Callable[[str], anthropic.Anthropic] = lambda api_key: anthropic.Anthropic(  # noqa: E731
    api_key=api_key
)


def create_client(api_key: str) -> anthropic.Anthropic:
    return _client_factory(api_key)


def validate_api_key(api_key: str, model: str) -> None:
    """Check that the key works and can use the model, without spending tokens."""
    try:
        create_client(api_key).models.retrieve(model)
    except (
        anthropic.AuthenticationError,
        anthropic.PermissionDeniedError,
        anthropic.NotFoundError,
    ) as exc:
        raise InvalidApiKeyError from exc
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
        raise ProviderUnavailableError from exc


def _to_provider_error(exc: Exception) -> ProviderError:
    if isinstance(exc, anthropic.AuthenticationError):
        return ProviderError("invalid_key")
    if isinstance(exc, anthropic.PermissionDeniedError):
        return ProviderError("key_without_access")
    if isinstance(exc, anthropic.RateLimitError):
        return ProviderError("rate_limited")
    if isinstance(exc, anthropic.APIStatusError) and exc.status_code < 500:
        return ProviderError("provider_rejected")
    return ProviderError("provider_unavailable")


_STOP_REASONS = {"refusal": "refusal", "max_tokens": "max_tokens", "tool_use": "tool_use"}


class AnthropicSession:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        system: str,
        tools: list[dict[str, Any]],
        history: list[tuple[str, str]],
        instruction: str,
    ) -> None:
        self._client = create_client(api_key)
        self._model = model
        self._system = system
        self._tools = tools
        self._messages: list[dict[str, Any]] = []
        for past_instruction, past_reply in history:
            self._messages.append({"role": "user", "content": past_instruction})
            self._messages.append({"role": "assistant", "content": past_reply})
        self._messages.append({"role": "user", "content": instruction})
        self._last_content: list[Any] = []
        self.last_turn = Turn()

    def stream_turn(self) -> Iterator[str]:
        try:
            with self._client.messages.stream(
                model=self._model,
                max_tokens=MAX_TOKENS,
                system=self._system,
                tools=self._tools,
                messages=self._messages,
                thinking={"type": "adaptive"},
                output_config={"effort": "medium"},
            ) as stream:
                for event in stream:
                    if event.type == "text":
                        yield event.text
                response = stream.get_final_message()
        except (anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
            raise _to_provider_error(exc) from exc

        self._last_content = response.content
        self.last_turn = Turn(
            text="".join(block.text for block in response.content if block.type == "text"),
            tool_calls=[
                ToolCall(id=block.id, name=block.name, input=block.input)
                for block in response.content
                if block.type == "tool_use"
            ],
            stop=_STOP_REASONS.get(response.stop_reason, "end"),
        )

    def add_tool_results(self, results: list[ToolResult]) -> None:
        # The assistant turn goes back unchanged (thinking blocks included), followed by
        # every tool result in a single user message.
        self._messages.append({"role": "assistant", "content": self._last_content})
        blocks = []
        for result in results:
            block: dict[str, Any] = {
                "type": "tool_result",
                "tool_use_id": result.call.id,
                "content": json.dumps(result.content, ensure_ascii=False),
            }
            if result.is_error:
                block["is_error"] = True
            blocks.append(block)
        self._messages.append({"role": "user", "content": blocks})
