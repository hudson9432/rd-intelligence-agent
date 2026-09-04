"""Structured, source-linked evidence model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, CheckConstraint, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.research_mission import ResearchMission
    from app.models.source_document import SourceDocument


class EvidenceCard(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "evidence_cards"
    __table_args__ = (
        CheckConstraint(
            "relevance_score >= 0 AND relevance_score <= 1",
            name="ck_evidence_relevance_score",
        ),
        CheckConstraint(
            "extraction_confidence >= 0 AND extraction_confidence <= 1",
            name="ck_evidence_extraction_confidence",
        ),
    )

    mission_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("research_missions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("source_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    problem: Mapped[str | None] = mapped_column(Text, nullable=True)
    method: Mapped[str | None] = mapped_column(Text, nullable=True)
    benchmark: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    limitation: Mapped[str | None] = mapped_column(Text, nullable=True)
    technology_tags_json: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    evidence_snippets_json: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False)
    extraction_confidence: Mapped[float] = mapped_column(Float, nullable=False)

    mission: Mapped[ResearchMission] = relationship(back_populates="evidence_cards")
    source: Mapped[SourceDocument] = relationship(back_populates="evidence_cards")
