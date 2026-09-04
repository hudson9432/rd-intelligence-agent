"""Persisted workflow event model."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.research_mission import ResearchMission


class AgentEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "agent_events"
    __table_args__ = (Index("ix_event_mission_created", "mission_id", "created_at"),)

    mission_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("research_missions.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )

    mission: Mapped[ResearchMission] = relationship(back_populates="agent_events")
