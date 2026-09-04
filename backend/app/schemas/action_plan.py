"""Executable PoC action-plan persistence contracts."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ActionTask(BaseModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    priority: str = Field(min_length=1)
    estimated_hours: float = Field(ge=0)
    dependencies: list[str] = Field(default_factory=list)
    status: str = Field(min_length=1)


class ActionPlanCreate(BaseModel):
    mission_id: UUID
    title: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1)
    tasks_json: list[ActionTask] = Field(default_factory=list)
    success_metrics_json: list[str] = Field(default_factory=list)
    estimated_effort: str = Field(min_length=1, max_length=100)


class ActionPlan(ActionPlanCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
