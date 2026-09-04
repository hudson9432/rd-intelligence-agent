"""Mission workflow graph, built on LangGraph.

    START -> Search -> Evidence -> Analysis
                                   |- research_required  -> bounded re-search
                                   |- ready_for_poc      -> Decision -> Action
                                   `- no_viable_direction -> Decision -> END

The orchestrator owns loop execution, iteration limits, routing, and event
emission. It never touches the database and never calls an external service:
stages are injected behind Protocols, so the same graph runs with mock,
partial, or real implementations.

Two rules from `AGENTS.md` shape how LangGraph is used here. Routing and
iteration limits stay in deterministic Python — the routers are pure functions
of state and the re-search bound is enforced in the analysis node, with
LangGraph's `recursion_limit` only as a backstop. And orchestration stays thin:
no scoring, parsing, or business rule lives in a node, only sequencing.

A failing stage records the failure in state instead of raising, so the graph
terminates through its normal edges and the state gathered so far survives.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Protocol
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph

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
Emit = Callable[..., None]

_EVENT_SINK_KEY = "workflow_event_sink"

#: Nodes per re-search round (search, evidence, analysis), plus headroom for
#: the final gate, decision, action, and LangGraph's own bookkeeping steps.
_NODES_PER_ROUND = 3
_RECURSION_HEADROOM = 8


class SearchStage(Protocol):
    """Phase 05. Turns a goal or targeted queries into normalized sources."""

    def search(
        self, *, goal: str, queries: Sequence[str], iteration: int
    ) -> Sequence[SourceResult]: ...


class EvidenceStage(Protocol):
    """Phase 06. Turns sources into persisted, provenance-checked evidence.

    Takes the goal because relevance is scored relative to it; an extractor
    that does not know what the mission is deciding cannot rate a source.
    """

    def extract(
        self, *, mission_id: UUID, goal: str, sources: Sequence[SourceResult]
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


def _emitter(config: RunnableConfig) -> Emit:
    """Pull the run's event sink out of the LangGraph config.

    The sink is per-run while the graph is compiled once, so it travels in
    `configurable` rather than being closed over at build time.
    """

    return config["configurable"][_EVENT_SINK_KEY]


def _failure(stage: WorkflowStage, error: Exception, emit: Emit) -> dict[str, Any]:
    emit(
        WorkflowOrchestrator.agent_name,
        "workflow_failed",
        f"Workflow stopped: {error}",
        failed_stage=stage.value,
    )
    return {"error": str(error), "failed_stage": stage}


class WorkflowOrchestrator:
    """Runs the mission graph to a terminal state."""

    agent_name = "orchestrator"

    def __init__(self, stages: WorkflowStages) -> None:
        self.stages = stages
        self._graph = self._build()

    # ------------------------------------------------------------------ graph

    def _build(self) -> Any:
        builder: StateGraph = StateGraph(WorkflowState)
        builder.add_node(WorkflowStage.SEARCH.value, self._search)
        builder.add_node(WorkflowStage.EVIDENCE.value, self._evidence)
        builder.add_node(WorkflowStage.ANALYSIS.value, self._analysis)
        builder.add_node(WorkflowStage.DECISION.value, self._decision)
        builder.add_node(WorkflowStage.ACTION.value, self._action)

        builder.add_edge(START, WorkflowStage.SEARCH.value)
        builder.add_conditional_edges(
            WorkflowStage.SEARCH.value,
            _route_after_search,
            {WorkflowStage.EVIDENCE.value: WorkflowStage.EVIDENCE.value, END: END},
        )
        builder.add_conditional_edges(
            WorkflowStage.EVIDENCE.value,
            _route_after_evidence,
            {WorkflowStage.ANALYSIS.value: WorkflowStage.ANALYSIS.value, END: END},
        )
        builder.add_conditional_edges(
            WorkflowStage.ANALYSIS.value,
            _route_after_analysis,
            {
                WorkflowStage.SEARCH.value: WorkflowStage.SEARCH.value,
                WorkflowStage.ANALYSIS.value: WorkflowStage.ANALYSIS.value,
                WorkflowStage.DECISION.value: WorkflowStage.DECISION.value,
                END: END,
            },
        )
        builder.add_conditional_edges(
            WorkflowStage.DECISION.value,
            _route_after_decision,
            {WorkflowStage.ACTION.value: WorkflowStage.ACTION.value, END: END},
        )
        builder.add_edge(WorkflowStage.ACTION.value, END)
        return builder.compile()

    # ------------------------------------------------------------------- run

    def run(
        self, state: WorkflowState, *, on_event: EventSink | None = None
    ) -> WorkflowRunResult:
        events: list[WorkflowEvent] = []

        def emit(
            agent_name: str, event_type: str, message: str, **metadata: object
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

        config: RunnableConfig = {
            "configurable": {_EVENT_SINK_KEY: emit},
            "recursion_limit": _NODES_PER_ROUND * (state.max_iterations + 1)
            + _RECURSION_HEADROOM,
        }

        try:
            raw = self._graph.invoke(state, config=config)
            final = WorkflowState.model_validate(raw)
        except GraphRecursionError as error:
            # The in-node iteration bound should always trip first; this is the
            # backstop that keeps a routing bug from running forever.
            emit(
                self.agent_name,
                "workflow_failed",
                f"Workflow stopped: {error}",
                failed_stage=WorkflowStage.ANALYSIS.value,
            )
            return WorkflowRunResult(
                mission_id=state.mission_id,
                status="failed",
                final_stage=WorkflowStage.ANALYSIS,
                iterations_used=state.max_iterations,
                events=events,
                error=f"The workflow graph exceeded its step limit: {error}",
            )

        if final.error is not None:
            return WorkflowRunResult(
                mission_id=final.mission_id,
                status="failed",
                final_stage=final.failed_stage or WorkflowStage.DONE,
                iterations_used=final.iteration,
                handoff_status=final.handoff.status if final.handoff else None,
                decision=final.decision,
                events=events,
                error=final.error,
            )

        emit(
            self.agent_name,
            "workflow_completed",
            "Workflow reached a terminal state.",
            iterations_used=final.iteration,
            handoff_status=final.handoff.status if final.handoff else None,
        )

        return WorkflowRunResult(
            mission_id=final.mission_id,
            status="completed",
            final_stage=WorkflowStage.DONE,
            iterations_used=final.iteration,
            handoff_status=final.handoff.status if final.handoff else None,
            decision=final.decision,
            action_plan=final.action_plan,
            poc_candidates=list(final.handoff.poc_candidates) if final.handoff else [],
            evidence_count=len(final.evidence),
            events=events,
        )

    # ----------------------------------------------------------------- nodes

    def _search(
        self, state: WorkflowState, config: RunnableConfig
    ) -> dict[str, Any]:
        emit = _emitter(config)
        try:
            found = list(
                self.stages.search.search(
                    goal=state.goal,
                    queries=list(state.queries),
                    iteration=state.iteration,
                )
            )
        except WorkflowStageError as error:
            return _failure(WorkflowStage.SEARCH, error, emit)

        emit(
            "search",
            "sources_retrieved",
            f"Retrieved {len(found)} source(s) for {len(state.queries)} query/queries.",
            iteration=state.iteration,
            queries=list(state.queries),
            source_count=len(found),
        )
        return {"sources": found}

    def _evidence(
        self, state: WorkflowState, config: RunnableConfig
    ) -> dict[str, Any]:
        emit = _emitter(config)
        try:
            extracted = list(
                self.stages.evidence.extract(
                    mission_id=state.mission_id,
                    goal=state.goal,
                    sources=state.sources,
                )
            )
        except WorkflowStageError as error:
            return _failure(WorkflowStage.EVIDENCE, error, emit)

        # Re-search adds to the evidence pool rather than replacing it, so a
        # later round is judged on everything gathered so far.
        known = {card.id for card in state.evidence}
        merged = [*state.evidence, *(c for c in extracted if c.id not in known)]
        emit(
            "evidence",
            "evidence_extracted",
            f"Extracted {len(extracted)} evidence card(s); "
            f"{len(merged)} held in total.",
            iteration=state.iteration,
            extracted_count=len(extracted),
            total_count=len(merged),
        )
        return {"evidence": merged}

    def _analysis(
        self, state: WorkflowState, config: RunnableConfig
    ) -> dict[str, Any]:
        emit = _emitter(config)
        try:
            handoff = self.stages.analysis.analyze(
                mission_goal=state.goal,
                evidence=list(state.evidence),
                research_exhausted=state.research_exhausted,
            )
        except WorkflowStageError as error:
            return _failure(WorkflowStage.ANALYSIS, error, emit)

        emit(
            "analysis",
            "handoff_produced",
            f"Analysis handoff: {handoff.status}. {handoff.reason}",
            iteration=state.iteration,
            handoff_status=handoff.status,
            poc_candidate_count=len(handoff.poc_candidates),
        )
        update: dict[str, Any] = {"handoff": handoff}

        if handoff.status != "research_required":
            return update

        request = handoff.research_request
        if request is None:  # pragma: no cover - forbidden by PhaseCHandoff
            return update | _failure(
                WorkflowStage.ANALYSIS,
                WorkflowStageError(
                    "A research-required handoff arrived without a research request."
                ),
                emit,
            )

        if state.research_exhausted:
            # The budget was already spent and the gate still asks for more, so
            # the loop would not terminate. Fail loudly instead of spinning.
            return update | _failure(
                WorkflowStage.ANALYSIS,
                WorkflowStageError(
                    "Analysis requested more research after the budget was exhausted."
                ),
                emit,
            )

        if state.iteration >= state.max_iterations:
            emit(
                self.agent_name,
                "research_budget_exhausted",
                f"Re-search limit of {state.max_iterations} reached; "
                "requesting a final viability decision.",
                iteration=state.iteration,
                max_iterations=state.max_iterations,
            )
            return update | {"research_exhausted": True}

        emit(
            self.agent_name,
            "targeted_research_started",
            f"Re-search round {state.iteration + 1} of {state.max_iterations}: "
            f"{request.reason}",
            iteration=state.iteration + 1,
            queries=list(request.queries),
            direction_ids=list(request.direction_ids),
            claim_ids=list(request.claim_ids),
        )
        return update | {
            "iteration": state.iteration + 1,
            "queries": list(request.queries),
        }

    def _decision(
        self, state: WorkflowState, config: RunnableConfig
    ) -> dict[str, Any]:
        emit = _emitter(config)
        if state.handoff is None:  # pragma: no cover - unreachable via routing
            return _failure(
                WorkflowStage.DECISION,
                WorkflowStageError("Decision reached without an analysis handoff."),
                emit,
            )

        try:
            decision = self.stages.decision.decide(
                mission_goal=state.goal, handoff=state.handoff
            )
        except WorkflowStageError as error:
            return _failure(WorkflowStage.DECISION, error, emit)

        emit(
            "decision",
            "decision_made",
            f"Decision: {decision.recommendation}. {decision.rationale}",
            recommendation=decision.recommendation,
            selected_direction_id=decision.selected_direction_id,
        )
        return {"decision": decision}

    def _action(self, state: WorkflowState, config: RunnableConfig) -> dict[str, Any]:
        emit = _emitter(config)
        if state.handoff is None or state.decision is None:  # pragma: no cover
            return _failure(
                WorkflowStage.ACTION,
                WorkflowStageError("Action reached without a decision."),
                emit,
            )

        try:
            plan = self.stages.action.plan(
                mission_id=state.mission_id,
                handoff=state.handoff,
                decision=state.decision,
            )
        except WorkflowStageError as error:
            return _failure(WorkflowStage.ACTION, error, emit)

        if plan is None:
            emit(
                "action",
                "action_plan_skipped",
                "No PoC task plan was produced for the selected direction.",
                selected_direction_id=state.decision.selected_direction_id,
            )
            return {}

        emit(
            "action",
            "action_plan_created",
            f"PoC plan '{plan.title}' with {len(plan.tasks_json)} task(s).",
            task_count=len(plan.tasks_json),
            estimated_effort=plan.estimated_effort,
        )
        return {"action_plan": plan}


# --------------------------------------------------------------------- routers
# Pure functions of state: every side effect and state change happens in a node.


def _route_after_search(state: WorkflowState) -> str:
    return END if state.error else WorkflowStage.EVIDENCE.value


def _route_after_evidence(state: WorkflowState) -> str:
    return END if state.error else WorkflowStage.ANALYSIS.value


def _route_after_analysis(state: WorkflowState) -> str:
    if state.error or state.handoff is None:
        return END
    if state.handoff.status != "research_required":
        return WorkflowStage.DECISION.value
    # The node has already applied the bound: once it flags the budget as
    # exhausted, the gate is asked once more instead of searching again.
    if state.research_exhausted:
        return WorkflowStage.ANALYSIS.value
    return WorkflowStage.SEARCH.value


def _route_after_decision(state: WorkflowState) -> str:
    if state.error or state.decision is None:
        return END
    if state.decision.recommendation != "proceed_with_poc":
        return END
    return WorkflowStage.ACTION.value
