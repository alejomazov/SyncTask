from typing import Annotated

from pydantic import BaseModel, StringConstraints, field_validator

from app.integrations.llm import catalog
from app.integrations.llm.catalog import AiProvider
from app.models.user_settings import ExecutionMode

CUSTOM_INSTRUCTIONS_MAX_LENGTH = 2000


class AiModelOption(BaseModel):
    id: str
    name: str
    provider: AiProvider


class AiProviderStatus(BaseModel):
    id: AiProvider
    name: str
    key_configured: bool
    key_last4: str | None


class SettingsRead(BaseModel):
    execution_mode: ExecutionMode
    ai_model: str
    ai_provider: AiProvider
    custom_instructions: str | None
    custom_instructions_max_length: int
    # True when the provider of the selected model has a key, so the assistant can be used.
    assistant_ready: bool
    providers: list[AiProviderStatus]
    available_models: list[AiModelOption]


class SettingsUpdate(BaseModel):
    """Partial update: only the fields present in the request are changed."""

    execution_mode: ExecutionMode | None = None
    ai_model: str | None = None
    # An empty text removes the instructions.
    custom_instructions: (
        Annotated[
            str,
            StringConstraints(strip_whitespace=True, max_length=CUSTOM_INSTRUCTIONS_MAX_LENGTH),
        ]
        | None
    ) = None

    @field_validator("ai_model")
    @classmethod
    def _known_model(cls, value: str | None) -> str | None:
        if value is not None and not catalog.is_known_model(value):
            raise ValueError("unknown model")
        return value


class AiKeyUpdate(BaseModel):
    api_key: Annotated[str, StringConstraints(strip_whitespace=True, min_length=20, max_length=300)]
