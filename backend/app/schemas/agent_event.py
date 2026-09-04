"""Agent event persistence and API contracts."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class AgentEventCreate(BaseModel):
    mission_id: UUID
    agent_name: str = Field(min_length=1, max_length=100)
    event_type: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentEvent(AgentEventCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("metadata_json", "metadata"),
    )
    created_at: datetime
