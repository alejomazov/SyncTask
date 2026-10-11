"""Gemini, through the official Google GenAI SDK and the key each user provides."""

from collections.abc import Callable, Iterator
from typing import Any

import httpx
from google import genai
from google.genai import errors, types

from app.integrations.llm.base import (
    InvalidApiKeyError,
    ProviderError,
    ProviderUnavailableError,
    ToolCall,
    ToolResult,
    Turn,
)

MAX_OUTPUT_TOKENS = 16000

# Replaced in tests to avoid real network calls.
_client_factory: Callable[[str], genai.Client] = lambda api_key: genai.Client(api_key=api_key)  # noqa: E731

_REFUSAL_REASONS = {
    types.FinishReason.SAFETY,
    types.FinishReason.RECITATION,
    types.FinishReason.BLOCKLIST,
    types.FinishReason.PROHIBITED_CONTENT,
    types.FinishReason.SPII,
}
_INVALID_CALL_REASONS = {
    types.FinishReason.MALFORMED_FUNCTION_CALL,
    types.FinishReason.UNEXPECTED_TOOL_CALL,
}
_UNSUPPORTED_SCHEMA_KEYS = {"additionalProperties"}


def create_client(api_key: str) -> genai.Client:
    return _client_factory(api_key)


def validate_api_key(api_key: str, model: str) -> None:
    """Check that the key works and can use the model, without spending tokens."""
    # Keep a reference to the client: the SDK closes its HTTP connection when the client
    # object is garbage-collected, which would abort the request below.
    client = create_client(api_key)
    try:
        client.models.get(model=model)
    except errors.ClientError as exc:
        if exc.code == 429:
            raise ProviderUnavailableError from exc
        raise InvalidApiKeyError from exc
    except (errors.APIError, httpx.HTTPError) as exc:
        raise ProviderUnavailableError from exc


def _to_provider_error(exc: Exception) -> ProviderError:
    if isinstance(exc, errors.ClientError):
        if exc.code == 401 or (exc.code == 400 and "API key" in (exc.message or "")):
            return ProviderError("invalid_key")
        if exc.code in (403, 404):
            return ProviderError("key_without_access")
        if exc.code == 429:
            return ProviderError("rate_limited")
        return ProviderError("provider_rejected")
    return ProviderError("provider_unavailable")


def _clean_schema(schema: Any) -> Any:
    """Drop the JSON Schema keywords the Gemini API does not accept in tool parameters."""
    if isinstance(schema, dict):
        return {
            key: _clean_schema(value)
            for key, value in schema.items()
            if key not in _UNSUPPORTED_SCHEMA_KEYS
        }
    if isinstance(schema, list):
        return [_clean_schema(item) for item in schema]
    return schema


def to_function_declarations(tools: list[dict[str, Any]]) -> list[types.FunctionDeclaration]:
    return [
        types.FunctionDeclaration(
            name=tool["name"],
            description=tool["description"],
            parameters_json_schema=_clean_schema(tool["input_schema"]),
        )
        for tool in tools
    ]


def _text_content(role: str, text: str) -> types.Content:
    return types.Content(role=role, parts=[types.Part(text=text)])


class GeminiSession:
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
        self._config = types.GenerateContentConfig(
            system_instruction=system,
            tools=[types.Tool(function_declarations=to_function_declarations(tools))],
            # The assistant validates and executes the calls itself.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
        self._contents: list[types.Content] = []
        for past_instruction, past_reply in history:
            self._contents.append(_text_content("user", past_instruction))
            self._contents.append(_text_content("model", past_reply))
        self._contents.append(_text_content("user", instruction))
        # Ids we made up for calls the API returned without one; never sent back.
        self._generated_ids: set[str] = set()
        self.last_turn = Turn()

    def stream_turn(self) -> Iterator[str]:
        parts: list[types.Part] = []
        finish_reason: types.FinishReason | None = None
        blocked = False
        try:
            stream = self._client.models.generate_content_stream(
                model=self._model, contents=self._contents, config=self._config
            )
            for chunk in stream:
                if chunk.prompt_feedback and chunk.prompt_feedback.block_reason:
                    blocked = True
                if not chunk.candidates:
                    continue
                candidate = chunk.candidates[0]
                finish_reason = candidate.finish_reason or finish_reason
                for part in (candidate.content.parts if candidate.content else None) or []:
                    parts.append(part)
                    if part.text and not part.thought:
                        yield part.text
        except (errors.APIError, httpx.HTTPError) as exc:
            raise _to_provider_error(exc) from exc

        if parts:
            # The model's parts go back unchanged: function calls carry thought signatures
            # the API requires on the next request of the same turn.
            self._contents.append(types.Content(role="model", parts=parts))

        tool_calls = []
        for index, part in enumerate(parts):
            if not part.function_call:
                continue
            call_id = part.function_call.id
            if not call_id:
                call_id = f"call_{len(self._contents)}_{index}"
                self._generated_ids.add(call_id)
            tool_calls.append(
                ToolCall(
                    id=call_id,
                    name=part.function_call.name or "",
                    input=dict(part.function_call.args or {}),
                )
            )
        if blocked or finish_reason in _REFUSAL_REASONS:
            stop = "refusal"
        elif finish_reason == types.FinishReason.MAX_TOKENS:
            stop = "max_tokens"
        elif finish_reason in _INVALID_CALL_REASONS:
            stop = "invalid_tool_call"
        elif tool_calls:
            stop = "tool_use"
        else:
            stop = "end"

        self.last_turn = Turn(
            text="".join(part.text for part in parts if part.text and not part.thought),
            tool_calls=tool_calls,
            stop=stop,
        )

    def add_tool_results(self, results: list[ToolResult]) -> None:
        self._contents.append(
            types.Content(
                role="user",
                parts=[
                    types.Part(
                        function_response=types.FunctionResponse(
                            id=None if result.call.id in self._generated_ids else result.call.id,
                            name=result.call.name,
                            response={"error" if result.is_error else "result": result.content},
                        )
                    )
                    for result in results
                ],
            )
        )
