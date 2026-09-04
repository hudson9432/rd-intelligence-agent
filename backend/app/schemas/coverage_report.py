"""Evidence coverage persistence contracts."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

CoverageStatus = Literal["absent", "weak", "adequate"]


class CoverageReportCreate(BaseModel):
    mission_id: UUID
    overall_score: float = Field(ge=0, le=100)
    sufficient: bool
    dimension_status_json: dict[str, CoverageStatus] = Field(default_factory=dict)
    missing_evidence_json: list[str] = Field(default_factory=list)
    unsupported_claims_json: list[str] = Field(default_factory=list)
    suggested_queries_json: list[str] = Field(default_factory=list)
    iteration: int = Field(ge=1)


class CoverageReport(CoverageReportCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
