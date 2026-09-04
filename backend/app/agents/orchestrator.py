"""Deterministic mission workflow graph.

    START -> Search -> Evidence -> Analysis
                                   |- research_required -> bounded re-search
                                   |- ready_for_poc      -> Decision -> Action
                                   `- no_viable_direction -> Decision -> END

The orchestrator owns loop execution, iteration limits, routing, and event
emission. It never touches the database and never calls an external service:
stages are injected, so the same graph runs with mock, partial, or real
implementations.

Routing is plain typed Python rather than a graph framework. `AGENTS.md`
requires that routing and iteration limits stay in deterministic code and that
no framework is added while a small local abstraction is enough; the node and
router boundaries below are shaped so a LangGraph runtime can wrap them later
without changing stage implementations.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol
from uuid import UUID

from app.schemas.action_plan import ActionPlanCreate
from app.schemas.analysis import PhaseCHandoff
from app.schemas.evidence_card import EvidenceCard
from app.schemas.source_result import SourceResult
from app.schemas.workflow import (
    WorkflowDecision,
    WorkflowEvent,
    WorkflowRunResult,
    WorkflowStage,
    WorkflowState,
)


class WorkflowStageError(RuntimeError):
    """Raised by a stage that cannot produce a usable result."""


EventSink = Callable[[WorkflowEvent], None]


class SearchStage(Protocol):
    """Phase 05. Turns a goal or targeted queries into normalized sources."""

    def search(
        self, *, goal: str, queries: Sequence[str], iteration: int
    ) -> Sequence[SourceResult]: ...


class EvidenceStage(Protocol):
    """Phase 06. Turns sources into persisted, provenance-checked evidence."""

    def extract(
        self, *, mission_id: UUID, sources: Sequence[SourceResult]
    ) -> Sequence[EvidenceCard]: ...


class AnalysisStage(Protocol):
    """Phase C. Analyst, Critic, and the viability gate behind one handoff."""

    def analyze(
        self,
        *,
        mission_goal: str,
        evidence: Sequence[EvidenceCard],
        research_exhausted: bool,
    ) -> PhaseCHandoff: ...


class DecisionStage(Protocol):
    """Phase 10. Converts a handoff into a go/no-go recommendation."""

    def decide(
        self, *, mission_goal: str, handoff: PhaseCHandoff
    ) -> WorkflowDecision: ...


class ActionStage(Protocol):
    """Phase 11. Converts the selected PoC candidate into a task plan."""

    def plan(
        self,
        *,
        mission_id: UUID,
        handoff: PhaseCHandoff,
        decision: WorkflowDecision,
    ) -> ActionPlanCreate | None: ...


class WorkflowStages:
    """The five injected stage implementations."""

    def __init__(
        self,
        *,
        search: SearchStage,
        evidence: EvidenceStage,
        analysis: AnalysisStage,
        decision: DecisionStage,
        action: ActionStage,
    ) -> None:
        self.search = search
        self.evidence = evidence
        self.analysis = analysis
        self.decision = decision
        self.action = action


class WorkflowOrchestrator:
    """Runs the mission graph to a terminal state."""

    agent_name = "orchestrator"

    def __init__(self, stages: WorkflowStages) -> None:
        self.stages = stages

    def run(
        self, state: WorkflowState, *, on_event: EventSink | None = None
    ) -> WorkflowRunResult:
        events: list[WorkflowEvent] = []

        def emit(
            agent_name: str,
            event_type: str,
            message: str,
            **metadata: object,
        ) -> None:
            event = WorkflowEvent(
                agent_name=agent_name,
                event_type=event_type,
                message=message,
                metadata=dict(metadata),
            )
            events.append(event)
            if on_event is not None:
                on_event(event)

        if not state.queries:
            state.queries = [state.goal]

        emit(
            self.agent_name,
            "workflow_started",
            f"Workflow started for mission goal: {state.goal}",
            max_iterations=state.max_iterations,
        )

        stage = WorkflowStage.SEARCH
        try:
            while stage is not WorkflowStage.DONE:
                stage = self._step(stage, state, emit)
        except WorkflowStageError as error:
            emit(
                self.agent_name,
                "workflow_failed",
                f"Workflow stopped: {error}",
                failed_stage=stage.value,
            )
            return WorkflowRunResult(
                mission_id=state.mission_id,
                status="failed",
                final_stage=stage,
                iterations_used=state.iteration,
                handoff_status=state.handoff.status if state.handoff else None,
                decision=state.decision,
                events=events,
                error=str(error),
            )

        emit(
            self.agent_name,
            "workflow_completed",
            "Workflow reached a terminal state.",
            iterations_used=state.iteration,
            handoff_status=state.handoff.status if state.handoff else None,
        )

        return WorkflowRunResult(
            mission_id=state.mission_id,
            status="completed",
            final_stage=WorkflowStage.DONE,
            iterations_used=state.iteration,
            handoff_status=state.handoff.status if state.handoff else None,
            decision=state.decision,
            action_plan=state.action_plan,
            poc_candidates=list(state.handoff.poc_candidates) if state.handoff else [],
            events=events,
        )

    def _step(
        self,
        stage: WorkflowStage,
        state: WorkflowState,
        emit: Callable[..., None],
    ) -> WorkflowStage:
        match stage:
            case WorkflowStage.SEARCH:
                return self._search(state, emit)
            case WorkflowStage.EVIDENCE:
                return self._evidence(state, emit)
            case WorkflowStage.ANALYSIS:
                return self._analysis(state, emit)
            case WorkflowStage.DECISION:
                return self._decision(state, emit)
            case WorkflowStage.ACTION:
                return self._action(state, emit)
            case _:  # pragma: no cover - the loop exits on DONE
                raise WorkflowStageError(f"Unroutable stage: {stage}")

    def _search(
        self, state: WorkflowState, emit: Callable[..., None]
    ) -> WorkflowStage:
        found = list(
            self.stages.search.search(
                goal=state.goal,
                queries=list(state.queries),
                iteration=state.iteration,
            )
        )
        state.sources = found
        emit(
            "search",
            "sources_retrieved",
            f"Retrieved {len(found)} source(s) for {len(state.queries)} query/queries.",
            iteration=state.iteration,
            queries=list(state.queries),
            source_count=len(found),
        )
        return WorkflowStage.EVIDENCE

    def _evidence(
        self, state: WorkflowState, emit: Callable[..., None]
    ) -> WorkflowStage:
        extracted = list(
            self.stages.evidence.extract(
                mission_id=state.mission_id, sources=state.sources
            )
        )
        # Re-search adds to the evidence pool rather than replacing it, so a
        # later round is judged on everything gathered so far.
        known = {card.id for card in state.evidence}
        state.evidence.extend(card for card in extracted if card.id not in known)
        emit(
            "evidence",
            "evidence_extracted",
            f"Extracted {len(extracted)} evidence card(s); "
            f"{len(state.evidence)} held in total.",
            iteration=state.iteration,
            extracted_count=len(extracted),
            total_count=len(state.evidence),
        )
        return WorkflowStage.ANALYSIS

    def _analysis(
        self, state: WorkflowState, emit: Callable[..., None]
    ) -> WorkflowStage:
        handoff = self.stages.analysis.analyze(
            mission_goal=state.goal,
            evidence=list(state.evidence),
            research_exhausted=state.research_exhausted,
        )
        state.handoff = handoff
        emit(
            "analysis",
            "handoff_produced",
            f"Analysis handoff: {handoff.status}. {handoff.reason}",
            iteration=state.iteration,
            handoff_status=handoff.status,
            poc_candidate_count=len(handoff.poc_candidates),
        )

        if handoff.status != "research_required":
            return WorkflowStage.DECISION

        request = handoff.research_request
        if request is None:  # pragma: no cover - forbidden by PhaseCHandoff
            raise WorkflowStageError(
                "A research-required handoff arrived without a research request."
            )

        if state.research_exhausted:
            # The budget was already spent and the gate still asks for more, so
            # the loop would not terminate. Fail loudly instead of spinning.
            raise WorkflowStageError(
                "Analysis requested more research after the budget was exhausted."
            )

        if state.iteration >= state.max_iterations:
            state.research_exhausted = True
            emit(
                self.agent_name,
                "research_budget_exhausted",
                f"Re-search limit of {state.max_iterations} reached; "
                "requesting a final viability decision.",
                iteration=state.iteration,
                max_iterations=state.max_iterations,
            )
            return WorkflowStage.ANALYSIS

        state.iteration += 1
        state.queries = list(request.queries)
        emit(
            self.agent_name,
            "targeted_research_started",
            f"Re-search round {state.iteration} of {state.max_iterations}: "
            f"{request.reason}",
            iteration=state.iteration,
            queries=list(request.queries),
            direction_ids=list(request.direction_ids),
            claim_ids=list(request.claim_ids),
        )
        return WorkflowStage.SEARCH

    def _decision(
        self, state: WorkflowState, emit: Callable[..., None]
    ) -> WorkflowStage:
        if state.handoff is None:  # pragma: no cover - unreachable via _analysis
            raise WorkflowStageError("Decision reached without an analysis handoff.")

        decision = self.stages.decision.decide(
            mission_goal=state.goal, handoff=state.handoff
        )
        state.decision = decision
        emit(
            "decision",
            "decision_made",
            f"Decision: {decision.recommendation}. {decision.rationale}",
            recommendation=decision.recommendation,
            selected_direction_id=decision.selected_direction_id,
        )

        if decision.recommendation != "proceed_with_poc":
            return WorkflowStage.DONE
        return WorkflowStage.ACTION

    def _action(
        self, state: WorkflowState, emit: Callable[..., None]
    ) -> WorkflowStage:
        if state.handoff is None or state.decision is None:  # pragma: no cover
            raise WorkflowStageError("Action reached without a decision.")

        plan = self.stages.action.plan(
            mission_id=state.mission_id,
            handoff=state.handoff,
            decision=state.decision,
        )
        state.action_plan = plan
        if plan is None:
            emit(
                "action",
                "action_plan_skipped",
                "No PoC task plan was produced for the selected direction.",
                selected_direction_id=state.decision.selected_direction_id,
            )
        else:
            emit(
                "action",
                "action_plan_created",
                f"PoC plan '{plan.title}' with {len(plan.tasks_json)} task(s).",
                task_count=len(plan.tasks_json),
                estimated_effort=plan.estimated_effort,
            )
        return WorkflowStage.DONE
