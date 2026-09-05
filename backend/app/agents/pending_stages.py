"""Placeholder workflow stages for phases that are not implemented yet.

These exist so the orchestrator graph, its bounded re-search loop, and its
event stream can run and be tested today. They are deterministic, make no
external call, and — per invariant 1 in `AGENTS.md` — invent nothing: a stage
whose phase is unbuilt returns an empty result rather than plausible-looking
data.

Search, Evidence, and Analysis are no longer placeholders in the default stage
set. The fallback classes remain here for isolated orchestrator tests. Decision
and Action are the remaining runtime placeholders.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from app.schemas.action_plan import ActionPlanCreate
from app.schemas.analysis import PhaseCHandoff
from app.schemas.evidence_card import EvidenceCard
from app.schemas.search_agent import SearchAgentOutput
from app.schemas.source_result import SourceResult
from app.schemas.workflow import WorkflowDecision


class PendingSearchStage:
    """Empty Search fallback used only by isolated orchestrator tests."""

    def search(
        self,
        *,
        mission_id: UUID,
        goal: str,
        missing_evidence: Sequence[str],
        query_history: Sequence[str],
        iteration: int,
    ) -> SearchAgentOutput:
        del mission_id, goal, missing_evidence, query_history, iteration
        return SearchAgentOutput(
            generated_queries=[],
            retrieved_sources=[],
            notes="Search is not configured.",
        )


class PendingEvidenceStage:
    """Empty Evidence fallback used only by isolated orchestrator tests."""

    def extract(
        self, *, mission_id: UUID, goal: str, sources: Sequence[SourceResult]
    ) -> Sequence[EvidenceCard]:
        del mission_id, goal, sources
        return []


class PendingDecisionStage:
    """Phase 10 placeholder.

    Deterministically follows the Phase C gate rather than scoring anything:
    the real Decision Engine owns weighting and thresholds.
    """

    def decide(
        self,
        *,
        mission_goal: str,
        handoff: PhaseCHandoff,
        evidence: Sequence[EvidenceCard] = (),
    ) -> WorkflowDecision:
        del mission_goal, evidence
        if handoff.status == "ready_for_poc" and handoff.poc_candidates:
            candidate = handoff.poc_candidates[0]
            return WorkflowDecision(
                recommendation="proceed_with_poc",
                rationale=(
                    "Phase C reported an evidence-grounded PoC candidate: "
                    f"{candidate.title}."
                ),
                selected_direction_id=candidate.direction_id,
            )
        return WorkflowDecision(
            recommendation="do_not_proceed",
            rationale=f"Phase C reported {handoff.status}. {handoff.reason}",
        )


class PendingActionStage:
    """Phase 11 placeholder.

    Returns no plan rather than inventing PoC tasks, effort estimates, or
    success metrics for a direction it cannot reason about.
    """

    def plan(
        self,
        *,
        mission_id: UUID,
        handoff: PhaseCHandoff,
        decision: WorkflowDecision,
    ) -> ActionPlanCreate | None:
        del mission_id, handoff, decision
        return None
