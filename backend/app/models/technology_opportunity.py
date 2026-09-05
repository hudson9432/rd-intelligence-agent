"""Scored technology opportunity model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, CheckConstraint, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.research_mission import ResearchMission


class TechnologyOpportunity(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "technology_opportunities"
    __table_args__ = (
        CheckConstraint("novelty BETWEEN 1 AND 5", name="ck_opportunity_novelty"),
        CheckConstraint(
            "technical_maturity BETWEEN 1 AND 5",
            name="ck_opportunity_technical_maturity",
        ),
        CheckConstraint(
            "implementation_difficulty BETWEEN 1 AND 5",
            name="ck_opportunity_implementation_difficulty",
        ),
        CheckConstraint(
            "goal_alignment BETWEEN 1 AND 5",
            name="ck_opportunity_goal_alignment",
        ),
        CheckConstraint(
            "poc_feasibility BETWEEN 1 AND 5",
            name="ck_opportunity_poc_feasibility",
        ),
        CheckConstraint(
            "evidence_strength BETWEEN 1 AND 5",
            name="ck_opportunity_evidence_strength",
        ),
        CheckConstraint(
            "overall_score >= 0 AND overall_score <= 100",
            name="ck_opportunity_overall_score",
        ),
    )

    mission_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("research_missions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    related_evidence_ids_json: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    novelty: Mapped[int] = mapped_column(Integer, nullable=False)
    technical_maturity: Mapped[int] = mapped_column(Integer, nullable=False)
    implementation_difficulty: Mapped[int] = mapped_column(Integer, nullable=False)
    goal_alignment: Mapped[int] = mapped_column(Integer, nullable=False)
    poc_feasibility: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_strength: Mapped[int] = mapped_column(Integer, nullable=False)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)

    mission: Mapped[ResearchMission] = relationship(
        back_populates="technology_opportunities"
    )
