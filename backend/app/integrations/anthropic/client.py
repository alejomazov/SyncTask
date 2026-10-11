"""Access to the Claude API with the key each user provides."""

from collections.abc import Callable

import anthropic

DEFAULT_MODEL = "claude-opus-5-5"

# Models a user may choose for the assistant, most capable first.
AVAILABLE_MODELS: dict[str, str] = {
    "claude-fable-5-1": "Claude Fable 5.1",
    "claude-opus-5-5": "Claude Opus 5.5",
    "claude-sonnet-5-5": "Claude Sonnet 5.5",
    "claude-haiku-5-5": "Claude Haiku 5.5",
}

# Replaced in tests to avoid real network calls.
_client_factory: Callable[[str], anthropic.Anthropic] = lambda api_key: anthropic.Anthropic(  # noqa: E731
    api_key=api_key
)


class InvalidApiKeyError(Exception):
    """Anthropic rejected the key, or the key has no access to the model."""


class ProviderUnavailableError(Exception):
    """Anthropic could not be reached, so the key could not be checked."""


def create_client(api_key: str) -> anthropic.Anthropic:
    return _client_factory(api_key)


def resolve_model(model: str | None) -> str:
    """Return the model to use, falling back to the default if it is no longer offered."""
    return model if model in AVAILABLE_MODELS else DEFAULT_MODEL


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
