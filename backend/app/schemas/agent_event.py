"""Agent activity event schema."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(UTC)


class AgentEvent(BaseModel):
    """A traceable event emitted by a workflow agent."""

    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    agent_name: str = Field(min_length=1, max_length=100)
    event_type: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
