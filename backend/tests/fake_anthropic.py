"""In-memory stand-in for the Anthropic SDK client used by the assistant."""

import copy
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2

_REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def api_error(error_class: type[anthropic.APIStatusError], status: int) -> anthropic.APIStatusError:
    return error_class("error", response=httpx2.Response(status, request=_REQUEST), body=None)


def connection_error() -> anthropic.APIConnectionError:
    return anthropic.APIConnectionError(request=_REQUEST)


def reply(
    text: str = "",
    tool_calls: list[tuple[str, Any]] | None = None,
    stop_reason: str | None = None,
) -> SimpleNamespace:
    """Build a model response with optional text and tool calls."""
    content: list[SimpleNamespace] = [SimpleNamespace(type="thinking", thinking="", signature="s")]
    if text:
        content.append(SimpleNamespace(type="text", text=text))
    for index, (name, tool_input) in enumerate(tool_calls or []):
        content.append(
            SimpleNamespace(
                type="tool_use", id=f"toolu_{name}_{index}", name=name, input=tool_input
            )
        )
    default_stop = "tool_use" if tool_calls else "end_turn"
    return SimpleNamespace(content=content, stop_reason=stop_reason or default_stop)


class _Stream:
    def __init__(self, response: SimpleNamespace) -> None:
        self._response = response

    def __enter__(self) -> "_Stream":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def __iter__(self):
        yield SimpleNamespace(type="message_start")
        for block in self._response.content:
            if block.type == "text":
                middle = len(block.text) // 2
                for chunk in (block.text[:middle], block.text[middle:]):
                    if chunk:
                        yield SimpleNamespace(type="text", text=chunk)
            yield SimpleNamespace(type="content_block_stop")

    def get_final_message(self) -> SimpleNamespace:
        return self._response


class FakeAnthropic:
    def __init__(self) -> None:
        self.valid_keys = {"sk-ant-valid-key-0000000000001234"}
        self.models_error: Exception | None = None
        self.script: list[SimpleNamespace | Exception] = []
        self.requests: list[dict[str, Any]] = []
        self.keys_used: list[str] = []
        self.messages = SimpleNamespace(stream=self._stream)
        self.models = SimpleNamespace(retrieve=self._retrieve)
        self._key = ""

    def for_key(self, api_key: str) -> "FakeAnthropic":
        self._key = api_key
        self.keys_used.append(api_key)
        return self

    def _retrieve(self, model: str) -> SimpleNamespace:
        if self.models_error is not None:
            raise self.models_error
        if self._key not in self.valid_keys:
            raise api_error(anthropic.AuthenticationError, 401)
        return SimpleNamespace(id=model)

    def _stream(self, **kwargs: Any) -> _Stream:
        # The assistant keeps appending to `messages`; keep what was sent on this request.
        self.requests.append({**kwargs, "messages": copy.copy(kwargs["messages"])})
        if not self.script:
            raise AssertionError("Unexpected request to Claude: the script is exhausted")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return _Stream(item)
