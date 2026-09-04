"""Normalized external research source result."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(UTC)


class SourceType(StrEnum):
    """External sources the Search tool knows how to query."""

    ARXIV = "arxiv"
    GITHUB = "github"


class SourceResult(BaseModel):
    """A single normalized, deduplicated result from an external source.

    Every field must come from the source response. Unknown fields stay
    `None`/empty rather than guessed, per the product invariant against
    fabricating papers, repositories, or URLs.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    source_type: SourceType
    title: str = Field(min_length=1, max_length=500)
    url: str = Field(min_length=1)
    normalized_url: str = Field(min_length=1)
    content_hash: str = Field(min_length=1)
    summary: str | None = None
    authors: list[str] = Field(default_factory=list)
    published_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    retrieved_at: datetime = Field(default_factory=utc_now)


class SourceError(BaseModel):
    """A typed, recorded failure for a single source, not a fabricated result."""

    model_config = ConfigDict(extra="forbid")

    source_type: SourceType
    message: str = Field(min_length=1)


class SourceSearchRequest(BaseModel):
    """Request contract for POST /research/search."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=500)
    max_results: int = Field(default=10, ge=1, le=50)


class SourceSearchResponse(BaseModel):
    """Response contract for POST /research/search."""

    model_config = ConfigDict(extra="forbid")

    query: str
    results: list[SourceResult]
    errors: list[SourceError] = Field(default_factory=list)
