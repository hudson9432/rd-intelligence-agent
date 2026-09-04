"""Typed input and output contracts for Search query planning."""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.source_result import SourceResult

SearchQuery = Annotated[str, Field(min_length=1, max_length=500)]


class SearchAgentInput(BaseModel):
    """Mission context supplied to the Search Agent for one workflow round."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    mission_id: UUID
    research_goal: str = Field(min_length=1)
    missing_evidence: list[str] = Field(default_factory=list)
    query_history: list[str] = Field(default_factory=list)
    iteration: int = Field(ge=0)


class SearchAgentOutput(BaseModel):
    """Bounded queries plus the source results retrieved with those queries."""

    model_config = ConfigDict(extra="forbid")

    generated_queries: list[SearchQuery] = Field(default_factory=list, max_length=4)
    retrieved_sources: list[SourceResult] = Field(default_factory=list)
    notes: str = Field(min_length=1)
