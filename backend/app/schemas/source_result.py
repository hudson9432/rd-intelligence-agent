"""Provider-neutral contracts for external research-source search."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SourceType(StrEnum):
    """External sources supported by the MVP search service."""

    ARXIV = "arxiv"
    GITHUB = "github"


def _normalize_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise ValueError("datetime must include a timezone")
    return value.astimezone(UTC)


class SourceResult(BaseModel):
    """Normalized source data before mission-scoped persistence."""

    model_config = ConfigDict(extra="forbid")

    source_type: SourceType
    title: str = Field(min_length=1, max_length=500)
    url: str = Field(min_length=1)
    published_at: datetime | None = None
    authors: list[str] = Field(default_factory=list)
    summary: str | None = None
    content: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    _normalize_published_at = field_validator("published_at")(_normalize_utc)


class SourceError(BaseModel):
    """A typed source failure returned without fabricating a result."""

    model_config = ConfigDict(extra="forbid")

    source_type: SourceType
    message: str = Field(min_length=1)


class SourceSearchRequest(BaseModel):
    """Request contract for ``POST /research/search``."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(min_length=1, max_length=500)
    sources: list[SourceType] = Field(
        default_factory=lambda: [SourceType.ARXIV, SourceType.GITHUB],
        min_length=1,
    )
    max_results_per_source: int = Field(default=5, ge=1, le=50)
    published_after: datetime | None = None

    _normalize_published_after = field_validator("published_after")(_normalize_utc)

    @field_validator("sources")
    @classmethod
    def reject_duplicate_sources(cls, value: list[SourceType]) -> list[SourceType]:
        if len(value) != len(set(value)):
            raise ValueError("sources must not contain duplicates")
        return value


class SourceSearchResponse(BaseModel):
    """Normalized results plus source-specific graceful failures."""

    model_config = ConfigDict(extra="forbid")

    query: str
    results: list[SourceResult]
    errors: list[SourceError] = Field(default_factory=list)
