"""Research evidence coverage report model."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.research_mission import ResearchMission


class CoverageReport(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "coverage_reports"
    __table_args__ = (
        UniqueConstraint(
            "mission_id", "iteration", name="uq_coverage_mission_iteration"
        ),
        CheckConstraint(
            "overall_score >= 0 AND overall_score <= 100",
            name="ck_coverage_overall_score",
        ),
        CheckConstraint("iteration >= 1", name="ck_coverage_iteration"),
    )

    mission_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("research_missions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    sufficient: Mapped[bool] = mapped_column(Boolean, nullable=False)
    dimension_status_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    missing_evidence_json: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    unsupported_claims_json: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    suggested_queries_json: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    iteration: Mapped[int] = mapped_column(Integer, nullable=False)

    mission: Mapped[ResearchMission] = relationship(back_populates="coverage_reports")
