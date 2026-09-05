"""Read-only aggregate for the mission dashboard; existing contracts stay stable."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.action_plan import ActionPlan
from app.schemas.agent_event import AgentEvent
from app.schemas.analysis import PocCandidate
from app.schemas.evidence_card import EvidenceCard
from app.schemas.research_mission import ResearchMissionDetail
from app.schemas.source_document import SourceDocument
from app.schemas.technology_opportunity import TechnologyOpportunity
from app.schemas.workflow import WorkflowDecision


class MissionRunSummary(BaseModel):
    iterations_used: int = Field(default=0, ge=0)
    handoff_status: (
        Literal["ready_for_poc", "research_required", "no_viable_direction"] | None
    ) = None
    evidence_count: int = Field(default=0, ge=0)
    query_history: list[str] = Field(default_factory=list)
    decision: WorkflowDecision | None = None
    poc_candidates: list[PocCandidate] = Field(default_factory=list)


class MissionWorkspace(BaseModel):
    mission: ResearchMissionDetail
    sources: list[SourceDocument]
    evidence: list[EvidenceCard]
    opportunities: list[TechnologyOpportunity]
    events: list[AgentEvent]
    run_started_at: datetime | None = None
    summary: MissionRunSummary | None = None
    action_plan: ActionPlan | None = None
    error: str | None = None
