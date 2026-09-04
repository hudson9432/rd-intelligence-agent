"""Normalized source document persistence contracts."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SourceDocumentCreate(BaseModel):
    mission_id: UUID
    source_type: str = Field(min_length=1, max_length=50)
    title: str = Field(min_length=1, max_length=500)
    url: str = Field(min_length=1)
    published_at: datetime | None = None
    authors_json: list[str] = Field(default_factory=list)
    raw_summary: str | None = None
    content: str | None = None
    content_hash: str = Field(min_length=64, max_length=64)


class SourceDocument(SourceDocumentCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
