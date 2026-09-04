"""Normalized result returned by every research-source integration."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class SourceResult(BaseModel):
    """Provider-neutral source data before mission-scoped persistence."""

    source_type: str = Field(min_length=1, max_length=50)
    title: str = Field(min_length=1, max_length=500)
    url: str = Field(min_length=1)
    published_at: datetime | None = None
    authors: list[str] = Field(default_factory=list)
    summary: str | None = None
    content: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("published_at")
    @classmethod
    def normalize_published_at(cls, value: datetime | None) -> datetime | None:
        """Require source timestamps to be unambiguous and normalize them to UTC."""

        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("published_at must include a timezone")
        return value.astimezone(UTC)
