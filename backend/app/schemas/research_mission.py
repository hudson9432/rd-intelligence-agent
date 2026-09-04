"""Research mission API contracts."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MissionStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ResearchMissionBase(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    goal: str = Field(min_length=1)


class ResearchMissionCreate(ResearchMissionBase):
    """Payload accepted when creating a mission."""


class ResearchMissionUpdate(BaseModel):
    """Fields that can be changed by application services."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    goal: str | None = Field(default=None, min_length=1)
    status: MissionStatus | None = None


class ResearchMissionSummary(ResearchMissionBase):
    """Stable mission response shared by list and detail endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: MissionStatus
    created_at: datetime
    updated_at: datetime


class ResearchMissionDetail(ResearchMissionSummary):
    """Mission detail response, ready for future aggregate fields."""


ResearchMission = ResearchMissionSummary
