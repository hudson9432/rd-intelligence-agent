"""Normalized external source model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UTCDateTime
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.evidence_card import EvidenceCard
    from app.models.research_mission import ResearchMission


class SourceDocument(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "source_documents"
    __table_args__ = (
        UniqueConstraint("mission_id", "url", name="uq_source_mission_url"),
        Index("ix_source_mission_hash", "mission_id", "content_hash"),
    )

    mission_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("research_missions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    authors_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    raw_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    mission: Mapped[ResearchMission] = relationship(back_populates="sources")
    evidence_cards: Mapped[list[EvidenceCard]] = relationship(
        back_populates="source", cascade="all, delete-orphan", passive_deletes=True
    )
