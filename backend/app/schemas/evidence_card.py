"""Structured evidence persistence contracts."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EvidenceCardCreate(BaseModel):
    mission_id: UUID
    source_id: UUID
    problem: str | None = None
    method: str | None = None
    benchmark: str | None = None
    result: str | None = None
    limitation: str | None = None
    technology_tags_json: list[str] = Field(default_factory=list)
    evidence_snippets_json: list[str] = Field(default_factory=list)
    relevance_score: float = Field(ge=0, le=1)
    extraction_confidence: float = Field(ge=0, le=1)


class EvidenceCard(EvidenceCardCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
