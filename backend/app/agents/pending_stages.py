"""Placeholder workflow stages for phases that are not implemented yet.

These exist so the orchestrator graph, its bounded re-search loop, and its
event stream can run and be tested today. They are deterministic, make no
external call, and — per invariant 1 in `AGENTS.md` — invent nothing: a stage
whose phase is unbuilt returns an empty result rather than plausible-looking
data.

With the default set wired end to end, a mission therefore runs Search →
Evidence → Analysis, exhausts its re-search budget with no evidence, and ends
at `no_viable_direction`. That outcome is truthful, not a simulation of
success. Replace each stage as its phase lands.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from app.schemas.action_plan import ActionPlanCreate
from app.schemas.analysis import PhaseCHandoff, TargetedResearchRequest
from app.schemas.evidence_card import EvidenceCard
from app.schemas.source_result import SourceResult
from app.schemas.workflow import WorkflowDecision


class PendingSearchStage:
    """Phase 05 placeholder. The phase 03 source tools are not wired in yet."""

    def search(
        self, *, goal: str, queries: Sequence[str], iteration: int
    ) -> Sequence[SourceResult]:
        del goal, queries, iteration
        return []


class PendingEvidenceStage:
    """Phase 06 placeholder.

    `EvidenceAgent` can already extract from a single source, but no service
    deduplicates, filters, persists, and events the result, so this returns
    nothing rather than producing unpersisted cards.
    """

    def extract(
        self, *, mission_id: UUID, sources: Sequence[SourceResult]
    ) -> Sequence[EvidenceCard]:
        del mission_id, sources
        return []


class PendingAnalysisStage:
    """Phase C placeholder.

    The real Analyst, Critic, and viability gate exist in `app/agents/analyst.py`,
    `app/agents/critic.py`, and `app/services/phase_c.py`, but they need
    `DirectionGenerator`, `CritiqueQuestionGenerator`, and `QuestionReviewer`
    providers that no adapter supplies yet. This mirrors what the real gate
    does with an empty evidence set: ask for research once, then report no
    viable direction when the budget is gone.
    """

    def analyze(
        self,
        *,
        mission_goal: str,
        evidence: Sequence[EvidenceCard],
        research_exhausted: bool,
    ) -> PhaseCHandoff:
        if evidence:
            return PhaseCHandoff(
                status="no_viable_direction",
                reason=(
                    "Evidence is available but no analysis provider is wired in, "
                    "so no direction can be judged."
                ),
            )

        if research_exhausted:
            return PhaseCHandoff(
                status="no_viable_direction",
                reason=(
                    "The re-search budget is exhausted and no evidence was "
                    "collected, so no direction has traceable support."
                ),
            )

        return PhaseCHandoff(
            status="research_required",
            research_request=TargetedResearchRequest(
                queries=[mission_goal],
                reason="No evidence has been collected for the mission goal.",
            ),
            reason="No evidence is available to support a feasible direction.",
        )


class PendingDecisionStage:
    """Phase 10 placeholder.

    Deterministically follows the Phase C gate rather than scoring anything:
    the real Decision Engine owns weighting and thresholds.
    """

    def decide(
        self, *, mission_goal: str, handoff: PhaseCHandoff
    ) -> WorkflowDecision:
        del mission_goal
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
