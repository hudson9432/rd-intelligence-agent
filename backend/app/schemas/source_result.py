"""Tentative raw search-result contract, ahead of the Research Sources owner.

This mirrors ``SourceDocumentCreate`` minus the mission-scoped persistence
fields, since a search result exists before it is attached to a mission. Treat
this as provisional until the team freezes the shared contracts; keep field
names aligned with ``SourceDocumentCreate`` to minimize rework when it lands.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class SourceResult(BaseModel):
    source_type: str = Field(min_length=1, max_length=50)
    title: str = Field(min_length=1, max_length=500)
    url: str = Field(min_length=1)
    published_at: datetime | None = None
    authors_json: list[str] = Field(default_factory=list)
    raw_summary: str | None = None
    content: str | None = None
    content_hash: str = Field(min_length=64, max_length=64)
