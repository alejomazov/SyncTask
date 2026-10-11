from typing import Annotated

from pydantic import BaseModel, StringConstraints

from app.models.user_settings import ExecutionMode


class SettingsRead(BaseModel):
    execution_mode: ExecutionMode
    ai_key_configured: bool
    ai_key_last4: str | None
    ai_model: str


class SettingsUpdate(BaseModel):
    execution_mode: ExecutionMode


class AiKeyUpdate(BaseModel):
    api_key: Annotated[str, StringConstraints(strip_whitespace=True, min_length=20, max_length=300)]
