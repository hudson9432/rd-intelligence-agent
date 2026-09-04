"""Persistent research mission model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UTCDateTime
from app.models.mixins import UUIDPrimaryKeyMixin, utc_now

if TYPE_CHECKING:
    from app.models.action_plan import ActionPlan
    from app.models.agent_event import AgentEvent
    from app.models.coverage_report import CoverageReport
    from app.models.evidence_card import EvidenceCard
    from app.models.source_document import SourceDocument
    from app.models.technology_opportunity import TechnologyOpportunity


class ResearchMission(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "research_missions"

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="created", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now, nullable=False
    )

    sources: Mapped[list[SourceDocument]] = relationship(
        back_populates="mission", cascade="all, delete-orphan", passive_deletes=True
    )
    evidence_cards: Mapped[list[EvidenceCard]] = relationship(
        back_populates="mission", cascade="all, delete-orphan", passive_deletes=True
    )
    technology_opportunities: Mapped[list[TechnologyOpportunity]] = relationship(
        back_populates="mission", cascade="all, delete-orphan", passive_deletes=True
    )
    coverage_reports: Mapped[list[CoverageReport]] = relationship(
        back_populates="mission", cascade="all, delete-orphan", passive_deletes=True
    )
    action_plan: Mapped[ActionPlan | None] = relationship(
        back_populates="mission",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    agent_events: Mapped[list[AgentEvent]] = relationship(
        back_populates="mission", cascade="all, delete-orphan", passive_deletes=True
    )
