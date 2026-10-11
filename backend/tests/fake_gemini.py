"""In-memory stand-in for the Google GenAI SDK client used by the assistant."""

from types import SimpleNamespace
from typing import Any

from google.genai import errors, types

SIGNATURE = b"thought-signature"


def api_error(code: int, message: str = "error", status: str = "ERROR") -> errors.APIError:
    error_class = errors.ClientError if code < 500 else errors.ServerError
    return error_class(code, {"error": {"code": code, "message": message, "status": status}})


def invalid_key_error() -> errors.APIError:
    return api_error(400, "API key not valid. Please pass a valid API key.", "INVALID_ARGUMENT")


def _chunk(
    parts: list[types.Part], finish_reason: types.FinishReason | None = None
) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(role="model", parts=parts), finish_reason=finish_reason
            )
        ]
    )


def reply(
    text: str = "",
    tool_calls: list[tuple[str, Any]] | None = None,
    finish_reason: types.FinishReason = types.FinishReason.STOP,
    call_ids: bool = False,
) -> list[types.GenerateContentResponse]:
    """Build the streamed chunks of a model response with optional text and function calls."""
    chunks = []
    if text:
        middle = len(text) // 2
        chunks.extend(_chunk([types.Part(text=piece)]) for piece in (text[:middle], text[middle:]))
    for index, (name, args) in enumerate(tool_calls or []):
        call = types.FunctionCall(name=name, args=args, id=f"fc_{index}" if call_ids else None)
        chunks.append(_chunk([types.Part(function_call=call, thought_signature=SIGNATURE)]))
    chunks.append(_chunk([], finish_reason))
    return chunks


def blocked_prompt() -> list[types.GenerateContentResponse]:
    feedback = types.GenerateContentResponsePromptFeedback(block_reason=types.BlockedReason.SAFETY)
    return [types.GenerateContentResponse(prompt_feedback=feedback)]


class FakeGemini:
    def __init__(self) -> None:
        self.valid_keys = {"AIzaSy-valid-gemini-key-00000000005678"}
        self.models_error: Exception | None = None
        self.script: list[list[types.GenerateContentResponse] | Exception] = []
        self.requests: list[dict[str, Any]] = []
        self.keys_used: list[str] = []
        self.models_checked: list[str] = []
        self.models = SimpleNamespace(
            get=self._get, generate_content_stream=self._generate_content_stream
        )
        self._key = ""

    def for_key(self, api_key: str) -> "FakeGemini":
        self._key = api_key
        self.keys_used.append(api_key)
        return self

    def _get(self, *, model: str) -> SimpleNamespace:
        self.models_checked.append(model)
        if self.models_error is not None:
            raise self.models_error
        if self._key not in self.valid_keys:
            raise invalid_key_error()
        return SimpleNamespace(name=f"models/{model}")

    def _generate_content_stream(self, *, model: str, contents: list, config: Any):
        # The session keeps appending to `contents`; keep what was sent on this request.
        self.requests.append({"model": model, "contents": list(contents), "config": config})
        if not self.script:
            raise AssertionError("Unexpected request to Gemini: the script is exhausted")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return iter(item)
