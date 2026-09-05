"""Workflow graph routing, loop bounds, and event stream."""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.agents.orchestrator import (
    WorkflowOrchestrator,
    WorkflowStageError,
    WorkflowStages,
)
from app.agents.pending_stages import (
    PendingActionStage,
    PendingDecisionStage,
    PendingEvidenceStage,
    PendingSearchStage,
)
from app.core.llm import MockLLMClient
from app.schemas.action_plan import ActionPlanCreate, ActionTask
from app.schemas.analysis import (
    EvaluatedClaim,
    PhaseCHandoff,
    PocCandidate,
    TargetedResearchRequest,
)
from app.schemas.evidence_card import EvidenceCard
from app.schemas.search_agent import SearchAgentOutput
from app.schemas.source_result import SourceResult
from app.schemas.workflow import WorkflowDecision, WorkflowStage, WorkflowState
from app.services.analysis_stage import PhaseCAnalysisStage

MISSION_ID = UUID("11111111-1111-1111-1111-111111111111")


def make_source(title: str) -> SourceResult:
    return SourceResult(
        source_type="arxiv",
        title=title,
        url=f"https://example.test/{title}",
    )


def make_evidence(card_id: UUID | None = None) -> EvidenceCard:
    return EvidenceCard(
        id=card_id or uuid4(),
        mission_id=MISSION_ID,
        source_id=uuid4(),
        relevance_score=0.8,
        extraction_confidence=0.7,
        created_at=datetime.now(UTC),
    )


def make_poc_handoff(direction_id: str = "d1") -> PhaseCHandoff:
    evidence_id = uuid4()
    return PhaseCHandoff(
        status="ready_for_poc",
        reason="One direction has traceable support.",
        poc_candidates=[
            PocCandidate(
                direction_id=direction_id,
                title="Quantized on-device inference",
                hypothesis="A 4-bit model meets the latency budget.",
                evidence_ids=[evidence_id],
                evidence_coverage=0.7,
                claim_assessments=[
                    EvaluatedClaim(
                        direction_id=direction_id,
                        claim_id="c1",
                        statement="4-bit quantization holds accuracy.",
                        is_core=True,
                        supporting_evidence_ids=[evidence_id],
                        support_strength=0.6,
                        verdict="supported",
                        rationale="Two independent sources agree.",
                    )
                ],
            )
        ],
    )


class RecordingSearch:
    """Search stage that records every call and returns scripted sources."""

    def __init__(self, batches: Sequence[Sequence[SourceResult]]) -> None:
        self.batches = list(batches)
        self.calls: list[tuple[int, list[str]]] = []
        self.histories: list[list[str]] = []

    def search(
        self,
        *,
        mission_id: UUID,
        goal: str,
        missing_evidence: Sequence[str],
        query_history: Sequence[str],
        iteration: int,
    ) -> SearchAgentOutput:
        del mission_id
        queries = list(missing_evidence) or [goal]
        self.calls.append((iteration, queries))
        self.histories.append(list(query_history))
        if iteration < len(self.batches):
            sources = list(self.batches[iteration])
        else:
            sources = []
        return SearchAgentOutput(
            generated_queries=queries[:4],
            retrieved_sources=sources,
            notes="Scripted search plan.",
        )


class ScriptedEvidence:
    def __init__(self, batches: Sequence[Sequence[EvidenceCard]]) -> None:
        self.batches = list(batches)
        self.call_count = 0

    def extract(
        self, *, mission_id: UUID, goal: str, sources: Sequence[SourceResult]
    ) -> Sequence[EvidenceCard]:
        del mission_id, goal, sources
        index = self.call_count
        self.call_count += 1
        return self.batches[index] if index < len(self.batches) else []


class ScriptedAnalysis:
    """Returns each scripted handoff in turn, repeating the last one."""

    def __init__(self, handoffs: Sequence[PhaseCHandoff]) -> None:
        self.handoffs = list(handoffs)
        self.calls: list[bool] = []
        self.seen_evidence: list[list[UUID]] = []

    def analyze(
        self,
        *,
        mission_goal: str,
        evidence: Sequence[EvidenceCard],
        research_exhausted: bool,
    ) -> PhaseCHandoff:
        del mission_goal
        index = min(len(self.calls), len(self.handoffs) - 1)
        self.calls.append(research_exhausted)
        self.seen_evidence.append([card.id for card in evidence])
        return self.handoffs[index]


class PlanningAction:
    def plan(
        self,
        *,
        mission_id: UUID,
        handoff: PhaseCHandoff,
        decision: WorkflowDecision,
    ) -> ActionPlanCreate:
        del handoff
        return ActionPlanCreate(
            mission_id=mission_id,
            title=f"PoC for {decision.selected_direction_id}",
            summary="Validate the core hypothesis in one week.",
            tasks_json=[
                ActionTask(
                    id="t1",
                    title="Benchmark the quantized model",
                    description="Measure latency and accuracy on the target device.",
                    addresses="claim-1",
                    priority="high",
                    estimated_hours=8,
                    status="todo",
                )
            ],
            success_metrics_json=["Latency under 50ms"],
            estimated_effort="1 week",
        )


class FailingSearch:
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
        raise WorkflowStageError("The source provider is unavailable.")


class FailingAnalysis:
    def analyze(
        self,
        *,
        mission_goal: str,
        evidence: Sequence[EvidenceCard],
        research_exhausted: bool,
    ) -> PhaseCHandoff:
        del mission_goal, evidence, research_exhausted
        raise WorkflowStageError("The analysis provider is unavailable.")


def build_stages(
    *,
    search: object | None = None,
    evidence: object | None = None,
    analysis: object | None = None,
    decision: object | None = None,
    action: object | None = None,
) -> WorkflowStages:
    return WorkflowStages(
        search=search or PendingSearchStage(),
        evidence=evidence or PendingEvidenceStage(),
        # The real Phase C gate, on the deterministic mock provider.
        analysis=analysis or PhaseCAnalysisStage(MockLLMClient()),
        decision=decision or PendingDecisionStage(),
        action=action or PendingActionStage(),
    )


def make_state(**overrides: object) -> WorkflowState:
    defaults: dict[str, object] = {
        "mission_id": MISSION_ID,
        "goal": "Decide whether to invest in on-device inference.",
    }
    defaults.update(overrides)
    return WorkflowState(**defaults)


def test_poc_ready_path_reaches_an_action_plan() -> None:
    stages = build_stages(
        search=RecordingSearch([[make_source("a")]]),
        evidence=ScriptedEvidence([[make_evidence()]]),
        analysis=ScriptedAnalysis([make_poc_handoff()]),
        action=PlanningAction(),
    )

    result = WorkflowOrchestrator(stages).run(make_state())

    assert result.status == "completed"
    assert result.final_stage is WorkflowStage.DONE
    assert result.handoff_status == "ready_for_poc"
    assert result.decision is not None
    assert result.decision.recommendation == "proceed_with_poc"
    assert result.decision.selected_direction_id == "d1"
    assert result.action_plan is not None
    assert result.action_plan.title == "PoC for d1"
    assert result.iterations_used == 0
    assert [event.event_type for event in result.events] == [
        "workflow_started",
        "queries_generated",
        "sources_retrieved",
        "evidence_extracted",
        "handoff_produced",
        "decision_made",
        "action_plan_created",
        "workflow_completed",
    ]


def test_no_viable_direction_stops_before_the_action_stage() -> None:
    handoff = PhaseCHandoff(
        status="no_viable_direction",
        reason="No direction survived the viability gate.",
    )
    stages = build_stages(analysis=ScriptedAnalysis([handoff]))

    result = WorkflowOrchestrator(stages).run(make_state())

    assert result.status == "completed"
    assert result.handoff_status == "no_viable_direction"
    assert result.action_plan is None
    assert "action_plan_created" not in [e.event_type for e in result.events]


def test_research_required_reruns_search_within_the_iteration_limit() -> None:
    research = PhaseCHandoff(
        status="research_required",
        reason="Support is too thin.",
        research_request=TargetedResearchRequest(
            queries=["quantization latency benchmark"],
            reason="Need latency measurements.",
        ),
    )
    search = RecordingSearch([[make_source("a")], [make_source("b")]])
    analysis = ScriptedAnalysis([research, research, make_poc_handoff()])
    stages = build_stages(
        search=search,
        evidence=ScriptedEvidence([[make_evidence()], [make_evidence()]]),
        analysis=analysis,
        action=PlanningAction(),
    )

    result = WorkflowOrchestrator(stages).run(make_state(max_iterations=2))

    assert result.status == "completed"
    assert result.handoff_status == "ready_for_poc"
    assert result.iterations_used == 2
    # Initial search plus one per re-search round.
    assert [iteration for iteration, _ in search.calls] == [0, 1, 2]
    # Re-search rounds use the targeted queries, not the original goal.
    assert search.calls[1][1] == ["quantization latency benchmark"]
    assert search.calls[2][1] == ["quantization latency benchmark"]
    assert search.histories == [
        [],
        ["Decide whether to invest in on-device inference."],
        [
            "Decide whether to invest in on-device inference.",
            "quantization latency benchmark",
        ],
    ]


def test_exhausted_budget_asks_analysis_once_more_without_searching_again() -> None:
    research = PhaseCHandoff(
        status="research_required",
        reason="Support is too thin.",
        research_request=TargetedResearchRequest(
            queries=["more evidence"], reason="Need more."
        ),
    )
    final = PhaseCHandoff(
        status="no_viable_direction",
        reason="The budget is spent and support is still missing.",
    )
    search = RecordingSearch([])
    # Three research_required rounds, then the gate concludes.
    analysis = ScriptedAnalysis([research, research, research, final])
    stages = build_stages(search=search, analysis=analysis)

    result = WorkflowOrchestrator(stages).run(make_state(max_iterations=2))

    assert result.status == "completed"
    assert result.handoff_status == "no_viable_direction"
    assert result.iterations_used == 2
    assert len(search.calls) == 3, "search must stop once the budget is spent"
    # The final analysis call is the only one told the budget is exhausted.
    assert analysis.calls == [False, False, False, True]
    assert "research_budget_exhausted" in [e.event_type for e in result.events]


def test_research_requested_after_exhaustion_fails_instead_of_looping() -> None:
    research = PhaseCHandoff(
        status="research_required",
        reason="Still not enough.",
        research_request=TargetedResearchRequest(
            queries=["again"], reason="Need more."
        ),
    )
    stages = build_stages(analysis=ScriptedAnalysis([research]))

    result = WorkflowOrchestrator(stages).run(make_state(max_iterations=1))

    assert result.status == "failed"
    assert result.error is not None
    assert "budget was exhausted" in result.error
    assert result.events[-1].event_type == "workflow_failed"


def test_evidence_accumulates_across_rounds_without_duplicates() -> None:
    shared = make_evidence()
    fresh = make_evidence()
    research = PhaseCHandoff(
        status="research_required",
        reason="Thin.",
        research_request=TargetedResearchRequest(queries=["more"], reason="Need more."),
    )
    analysis = ScriptedAnalysis([research, make_poc_handoff()])
    stages = build_stages(
        search=RecordingSearch([[make_source("a")], [make_source("b")]]),
        # The second round re-returns the same card plus a new one.
        evidence=ScriptedEvidence([[shared], [shared, fresh]]),
        analysis=analysis,
        action=PlanningAction(),
    )

    result = WorkflowOrchestrator(stages).run(make_state(max_iterations=2))

    # LangGraph threads a new state through each node, so assert on what the
    # analysis stage was actually handed rather than on the input object.
    assert analysis.seen_evidence == [[shared.id], [shared.id, fresh.id]]
    assert result.evidence_count == 2


def test_a_failing_stage_ends_the_run_as_failed() -> None:
    stages = build_stages(search=FailingSearch())

    result = WorkflowOrchestrator(stages).run(make_state())

    assert result.status == "failed"
    assert result.final_stage is WorkflowStage.SEARCH
    assert result.error == "The source provider is unavailable."
    assert result.events[-1].event_type == "workflow_failed"


def test_a_failed_run_reports_evidence_accumulated_before_the_failure() -> None:
    card = make_evidence()
    stages = build_stages(
        search=RecordingSearch([[make_source("a")]]),
        evidence=ScriptedEvidence([[card]]),
        analysis=FailingAnalysis(),
    )

    result = WorkflowOrchestrator(stages).run(make_state())

    assert result.status == "failed"
    assert result.final_stage is WorkflowStage.ANALYSIS
    assert result.evidence_count == 1


def test_events_stream_to_the_sink_as_they_happen() -> None:
    seen: list[str] = []
    stages = build_stages(analysis=ScriptedAnalysis([make_poc_handoff()]))

    result = WorkflowOrchestrator(stages).run(
        make_state(), on_event=lambda event: seen.append(event.event_type)
    )

    assert seen == [event.event_type for event in result.events]


def test_the_goal_reaches_the_first_search_when_no_evidence_gap_is_given() -> None:
    search = RecordingSearch([])
    stages = build_stages(
        search=search, analysis=ScriptedAnalysis([make_poc_handoff()])
    )
    state = make_state()

    WorkflowOrchestrator(stages).run(state)

    assert search.calls[0][1] == [state.goal]


def test_default_stages_end_at_no_viable_direction() -> None:
    """With no Search or Evidence stage, the real gate must report failure.

    This runs the actual Analyst, Critic, and viability gate on the mock
    provider, so the outcome comes from Phase C rather than from a stub.
    """

    result = WorkflowOrchestrator(build_stages()).run(make_state(max_iterations=2))

    assert result.status == "completed"
    assert result.handoff_status == "no_viable_direction"
    assert result.poc_candidates == []
    assert result.action_plan is None
    assert result.decision is not None
    assert result.decision.recommendation == "do_not_proceed"
    assert result.iterations_used == 2


def test_max_iterations_is_bounded_by_the_schema() -> None:
    with pytest.raises(ValueError):
        make_state(max_iterations=0)
    with pytest.raises(ValueError):
        make_state(max_iterations=6)


def test_the_graph_exposes_one_node_per_stage() -> None:
    """The graph is a real LangGraph, not a hand-rolled loop behind the name."""

    graph = WorkflowOrchestrator(build_stages())._graph.get_graph()

    assert {node for node in graph.nodes} == {
        "__start__",
        "__end__",
        "search",
        "evidence",
        "analysis",
        "decision",
        "action",
    }


def test_the_longest_legal_path_fits_inside_the_recursion_limit() -> None:
    """The step budget must cover the worst case the router can legally reach.

    With `max_iterations=5` that is six search rounds, the final gate, the
    decision, and the action plan. If the headroom were too small LangGraph
    would raise `GraphRecursionError` before the loop bound applied.
    """

    research = PhaseCHandoff(
        status="research_required",
        reason="Thin.",
        research_request=TargetedResearchRequest(queries=["more"], reason="Need more."),
    )
    search = RecordingSearch([])
    analysis = ScriptedAnalysis([research] * 6 + [make_poc_handoff()])
    stages = build_stages(search=search, analysis=analysis, action=PlanningAction())

    result = WorkflowOrchestrator(stages).run(make_state(max_iterations=5))

    assert result.status == "completed"
    assert result.iterations_used == 5
    assert len(search.calls) == 6
    assert result.action_plan is not None
