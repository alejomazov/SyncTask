"""Entry points the rest of the application uses to reach a language model."""

from typing import Any

from app.integrations.anthropic import client as anthropic_client
from app.integrations.gemini import client as gemini_client
from app.integrations.llm.base import ChatSession
from app.integrations.llm.catalog import AiProvider, provider_of

_VALIDATORS = {
    AiProvider.ANTHROPIC: anthropic_client.validate_api_key,
    AiProvider.GEMINI: gemini_client.validate_api_key,
}
_SESSIONS = {
    AiProvider.ANTHROPIC: anthropic_client.AnthropicSession,
    AiProvider.GEMINI: gemini_client.GeminiSession,
}


def validate_api_key(provider: AiProvider, api_key: str, model: str) -> None:
    """Raise InvalidApiKeyError or ProviderUnavailableError unless the key can use the model."""
    _VALIDATORS[provider](api_key, model)


def open_session(
    *,
    api_key: str,
    model: str,
    system: str,
    tools: list[dict[str, Any]],
    history: list[tuple[str, str]],
    instruction: str,
) -> ChatSession:
    return _SESSIONS[provider_of(model)](
        api_key=api_key,
        model=model,
        system=system,
        tools=tools,
        history=history,
        instruction=instruction,
    )
