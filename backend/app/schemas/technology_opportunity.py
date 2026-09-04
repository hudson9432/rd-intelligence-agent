"""Technology opportunity persistence contracts."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TechnologyOpportunityCreate(BaseModel):
    mission_id: UUID
    name: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1)
    related_evidence_ids_json: list[UUID] = Field(default_factory=list)
    novelty: int = Field(ge=1, le=5)
    technical_maturity: int = Field(ge=1, le=5)
    implementation_difficulty: int = Field(ge=1, le=5)
    business_impact: int = Field(ge=1, le=5)
    poc_feasibility: int = Field(ge=1, le=5)
    evidence_strength: int = Field(ge=1, le=5)
    overall_score: float = Field(ge=0, le=100)
    rationale: str = Field(min_length=1)


class TechnologyOpportunity(TechnologyOpportunityCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
