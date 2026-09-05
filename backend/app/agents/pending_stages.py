"""Placeholder workflow stages for phases that are not implemented yet.

These exist so the orchestrator graph, its bounded re-search loop, and its
event stream can run and be tested today. They are deterministic, make no
external call, and — per invariant 1 in `AGENTS.md` — invent nothing: a stage
whose phase is unbuilt returns an empty result rather than plausible-looking
data.

Analysis is no longer among them: `PhaseCAnalysisStage` runs the real
Analyst, Critic, and viability gate. Because Search and Evidence still return
nothing, a default run reaches that real gate with an empty evidence set,
exhausts its re-search budget, and ends at `no_viable_direction`. That outcome
is truthful, not a simulation of success. Replace each remaining stage as its
phase lands.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from app.schemas.action_plan import ActionPlanCreate
from app.schemas.analysis import PhaseCHandoff
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
