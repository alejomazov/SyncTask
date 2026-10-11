"""Providers and models a user may choose for the assistant."""

from dataclasses import dataclass
from enum import StrEnum


class AiProvider(StrEnum):
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"


PROVIDER_NAMES: dict[AiProvider, str] = {
    AiProvider.ANTHROPIC: "Claude (Anthropic)",
    AiProvider.GEMINI: "Gemini (Google)",
}


@dataclass(frozen=True)
class ModelOption:
    id: str
    name: str
    provider: AiProvider


# Within each provider, most capable first.
MODELS: tuple[ModelOption, ...] = (
    ModelOption("claude-fable-5-1", "Claude Fable 5.1", AiProvider.ANTHROPIC),
    ModelOption("claude-opus-5-5", "Claude Opus 5.5", AiProvider.ANTHROPIC),
    ModelOption("claude-sonnet-5-5", "Claude Sonnet 5.5", AiProvider.ANTHROPIC),
    ModelOption("claude-haiku-5-5", "Claude Haiku 5.5", AiProvider.ANTHROPIC),
    ModelOption("gemini-3.1-pro-preview", "Gemini 3.1 Pro (preview)", AiProvider.GEMINI),
    ModelOption("gemini-3.8-flash", "Gemini 3.8 Flash", AiProvider.GEMINI),
    ModelOption("gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite", AiProvider.GEMINI),
)

DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_MODEL_BY_PROVIDER: dict[AiProvider, str] = {
    AiProvider.ANTHROPIC: "claude-opus-5-5",
    AiProvider.GEMINI: "gemini-3.8-flash",
}

_BY_ID = {model.id: model for model in MODELS}


def is_known_model(model: str) -> bool:
    return model in _BY_ID


def resolve_model(model: str | None) -> str:
    """Return the model to use, falling back to the default if it is no longer offered."""
    return model if model in _BY_ID else DEFAULT_MODEL


def provider_of(model: str) -> AiProvider:
    return _BY_ID[resolve_model(model)].provider
