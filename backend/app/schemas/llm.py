"""Provider-independent LLM chat contracts."""

from typing import Literal

from pydantic import BaseModel, Field

LLMRole = Literal["system", "user", "assistant"]


class LLMMessage(BaseModel):
    role: LLMRole
    content: str = Field(min_length=1)


class LLMCompletion(BaseModel):
    content: str = Field(min_length=1)
    model: str = Field(min_length=1)
    mocked: bool
