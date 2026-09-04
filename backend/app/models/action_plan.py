"""Executable PoC action plan model."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.research_mission import ResearchMission


class ActionPlan(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "action_plans"
    __table_args__ = (UniqueConstraint("mission_id", name="uq_action_plan_mission"),)

    mission_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("research_missions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    tasks_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    success_metrics_json: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    estimated_effort: Mapped[str] = mapped_column(String(100), nullable=False)

    mission: Mapped[ResearchMission] = relationship(back_populates="action_plan")
