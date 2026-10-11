from typing import Annotated

from pydantic import BaseModel, StringConstraints, field_validator

from app.integrations.anthropic.client import AVAILABLE_MODELS
from app.models.user_settings import ExecutionMode


class AiModelOption(BaseModel):
    id: str
    name: str


class SettingsRead(BaseModel):
    execution_mode: ExecutionMode
    ai_key_configured: bool
    ai_key_last4: str | None
    ai_model: str
    available_models: list[AiModelOption]


class SettingsUpdate(BaseModel):
    """Partial update: only the fields present in the request are changed."""

    execution_mode: ExecutionMode | None = None
    ai_model: str | None = None

    @field_validator("ai_model")
    @classmethod
    def _known_model(cls, value: str | None) -> str | None:
        if value is not None and value not in AVAILABLE_MODELS:
            raise ValueError("unknown model")
        return value


class AiKeyUpdate(BaseModel):
    api_key: Annotated[str, StringConstraints(strip_whitespace=True, min_length=20, max_length=300)]
