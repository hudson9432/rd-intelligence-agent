"""Workflow orchestration contracts.

These types describe how the mission workflow moves between stages. Routing,
iteration limits, and stage results are deterministic and typed here so the
orchestrator itself stays thin, per the architecture rules in `AGENTS.md`.
"""

from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.action_plan import ActionPlanCreate
from app.schemas.analysis import PhaseCHandoff, PocCandidate
from app.schemas.evidence_card import EvidenceCard
from app.schemas.source_result import SourceResult


class WorkflowStage(StrEnum):
    """Nodes of the mission workflow graph."""

    SEARCH = "search"
    EVIDENCE = "evidence"
    ANALYSIS = "analysis"
    DECISION = "decision"
    ACTION = "action"
    DONE = "done"


class WorkflowDecision(BaseModel):
    """Provisional Decision Engine contract.

    Phase 10 owns the real scoring rules. The orchestrator only needs to know
    whether to build an action plan, so this deliberately stays minimal and is
    expected to be replaced rather than extended.
    """

    recommendation: Literal["proceed_with_poc", "do_not_proceed"]
    rationale: str = Field(min_length=1)
    selected_direction_id: str | None = None

    @model_validator(mode="after")
    def validate_selection(self) -> "WorkflowDecision":
        if self.recommendation == "proceed_with_poc" and not self.selected_direction_id:
            raise ValueError("Proceeding with a PoC requires a selected direction")
        return self


class WorkflowEvent(BaseModel):
    """A stage transition, emitted as the graph runs.

    The orchestrator is pure and never touches the database; the workflow
    service converts these into persisted `AgentEvent` rows.
    """

    agent_name: str = Field(min_length=1, max_length=100)
    event_type: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowState(BaseModel):
    """Everything the graph carries between stages."""

    model_config = ConfigDict(arbitrary_types_allowed=False)

    mission_id: UUID
    goal: str = Field(min_length=1)

    max_iterations: int = Field(default=2, ge=1, le=5)
    """Upper bound on targeted re-search rounds. Invariant 6 in `AGENTS.md`."""

    iteration: int = Field(default=0, ge=0)
    research_exhausted: bool = False

    queries: list[str] = Field(default_factory=list)
    sources: list[SourceResult] = Field(default_factory=list)
    evidence: list[EvidenceCard] = Field(default_factory=list)
    handoff: PhaseCHandoff | None = None
    decision: WorkflowDecision | None = None
    action_plan: ActionPlanCreate | None = None

    error: str | None = None
    """Set by a node when its stage fails. The routers send it straight to END.

    A failing stage records the failure in state rather than raising, so the
    graph terminates through its normal edges and the accumulated state stays
    available instead of being lost with the exception.
    """

    failed_stage: WorkflowStage | None = None


class WorkflowRunResult(BaseModel):
    """Terminal summary of one workflow run."""

    mission_id: UUID
    status: Literal["completed", "failed"]
    final_stage: WorkflowStage
    iterations_used: int
    handoff_status: Literal[
        "ready_for_poc", "research_required", "no_viable_direction"
    ] | None = None
    decision: WorkflowDecision | None = None
    action_plan: ActionPlanCreate | None = None
    poc_candidates: list[PocCandidate] = Field(default_factory=list)
    evidence_count: int = Field(default=0, ge=0)
    events: list[WorkflowEvent] = Field(default_factory=list)
    error: str | None = None
