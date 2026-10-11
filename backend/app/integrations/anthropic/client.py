"""Access to the Claude API with the key each user provides."""

from collections.abc import Callable

import anthropic

MODEL = "claude-opus-5-5"

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


def validate_api_key(api_key: str) -> None:
    """Check the key against Anthropic without spending tokens."""
    try:
        create_client(api_key).models.retrieve(MODEL)
    except (
        anthropic.AuthenticationError,
        anthropic.PermissionDeniedError,
        anthropic.NotFoundError,
    ) as exc:
        raise InvalidApiKeyError from exc
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
        raise ProviderUnavailableError from exc
