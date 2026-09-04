"""Phase C wired as the workflow's Analysis stage."""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.agents.evidence import EvidenceAgent
from app.agents.orchestrator import WorkflowOrchestrator, WorkflowStageError
from app.core.llm import LLMClient, MockLLMClient
from app.schemas.evidence_card import EvidenceCard
from app.schemas.llm import LLMCompletion, LLMMessage
from app.schemas.source_result import SourceResult
from app.services.analysis_stage import PhaseCAnalysisStage
from tests.test_workflow_orchestrator import (
    MISSION_ID,
    PlanningAction,
    RecordingSearch,
    build_stages,
    make_source,
    make_state,
)

GOAL = "Decide whether to invest in quantized on-device inference."


def evidence_card(
    result: str, snippet: str, limitation: str | None = None
) -> EvidenceCard:
    return EvidenceCard(
        id=uuid4(),
        mission_id=MISSION_ID,
        source_id=uuid4(),
        problem="On-device latency budget",
        method="4-bit quantization",
        benchmark="MobileBench",
        result=result,
        limitation=limitation,
        technology_tags_json=["quantization", "edge"],
        evidence_snippets_json=[snippet],
        relevance_score=0.9,
        extraction_confidence=0.85,
        created_at=datetime.now(UTC),
    )


def supported_evidence() -> list[EvidenceCard]:
    """Evidence whose recorded limitations let the Critic form a challenge.

    The mock question generator only omits a suggested search when a card
    records a limitation, which is what allows the critique to reach `ready`.
    """

    return [
        evidence_card(
            "38ms median latency",
            "4-bit quantization reached 38ms median latency.",
            "Measured on one device class only.",
        ),
        evidence_card(
            "1.2% accuracy drop",
            "Accuracy dropped by 1.2% after quantization.",
            "Evaluated on a single benchmark suite.",
        ),
    ]


class MalformedLLMClient(LLMClient):
    """A live-looking provider that returns something unparseable."""

    model_name = "broken"

    def complete(self, messages: list[LLMMessage]) -> LLMCompletion:
        del messages
        return LLMCompletion(content="not json at all", model="broken", mocked=False)


class SuppliedEvidence:
    """Evidence stage that hands the graph a fixed, already-persisted batch."""

    def __init__(self, cards: Sequence[EvidenceCard]) -> None:
        self.cards = list(cards)

    def extract(
        self, *, mission_id: UUID, sources: Sequence[SourceResult]
    ) -> Sequence[EvidenceCard]:
        del mission_id, sources
        return self.cards


def stage() -> PhaseCAnalysisStage:
    return PhaseCAnalysisStage(MockLLMClient())


def test_no_evidence_asks_for_research() -> None:
    handoff = stage().analyze(
        mission_goal=GOAL, evidence=[], research_exhausted=False
    )

    assert handoff.status == "research_required"
    assert handoff.research_request is not None
    assert handoff.poc_candidates == []


def test_no_evidence_with_the_budget_spent_reports_no_viable_direction() -> None:
    handoff = stage().analyze(
        mission_goal=GOAL, evidence=[], research_exhausted=True
    )

    assert handoff.status == "no_viable_direction"
    assert handoff.research_request is None
    assert handoff.poc_candidates == []


def test_evidence_without_limitations_yields_targeted_queries() -> None:
    """An accepted question carrying a suggested search still needs research."""

    evidence = [
        evidence_card("38ms median latency", "Quantization reached 38ms."),
        evidence_card("1.2% accuracy drop", "Accuracy fell by 1.2%."),
    ]

    handoff = stage().analyze(
        mission_goal=GOAL, evidence=evidence, research_exhausted=False
    )

    assert handoff.status == "research_required"
    assert handoff.research_request is not None
    assert 1 <= len(handoff.research_request.queries) <= 3
    # The queries are derived from the evidence, not from the bare goal.
    assert handoff.research_request.queries != [GOAL]


def test_supported_evidence_produces_a_grounded_poc_candidate() -> None:
    evidence = supported_evidence()
    supplied = {card.id for card in evidence}

    handoff = stage().analyze(
        mission_goal=GOAL, evidence=evidence, research_exhausted=False
    )

    assert handoff.status == "ready_for_poc"
    assert handoff.poc_candidates
    candidate = handoff.poc_candidates[0]
    # Invariant 2: every cited ID must trace back to the supplied evidence.
    assert set(candidate.evidence_ids) <= supplied
    assert candidate.claim_assessments
    for assessment in candidate.claim_assessments:
        assert set(assessment.supporting_evidence_ids) <= supplied
        assert assessment.verdict in {"supported", "contested", "unknown"}


def test_an_unparseable_provider_response_fails_the_stage() -> None:
    """Invariant 1: a broken provider must not be smoothed into an analysis."""

    broken = PhaseCAnalysisStage(MalformedLLMClient())

    with pytest.raises(WorkflowStageError, match="unusable response"):
        broken.analyze(
            mission_goal=GOAL,
            evidence=supported_evidence(),
            research_exhausted=False,
        )


def test_the_whole_graph_reaches_a_poc_plan_on_real_analysis() -> None:
    """End to end: sources -> evidence -> real Phase C -> decision -> plan."""

    evidence = supported_evidence()
    search = RecordingSearch([[make_source("a")]])
    stages = build_stages(
        search=search,
        evidence=SuppliedEvidence(evidence),
        analysis=stage(),
        action=PlanningAction(),
    )

    result = WorkflowOrchestrator(stages).run(make_state(goal=GOAL))

    assert result.status == "completed"
    assert result.handoff_status == "ready_for_poc"
    assert result.iterations_used == 0, "grounded evidence needs no re-search"
    assert result.evidence_count == len(evidence)
    assert result.decision is not None
    assert result.decision.recommendation == "proceed_with_poc"
    assert result.action_plan is not None
    assert [event.event_type for event in result.events] == [
        "workflow_started",
        "sources_retrieved",
        "evidence_extracted",
        "handoff_produced",
        "decision_made",
        "action_plan_created",
        "workflow_completed",
    ]


def extracted_cards(
    sources: Sequence[SourceResult], mission_goal: str
) -> list[EvidenceCard]:
    """Run real extraction, then assign the IDs persistence would assign."""

    agent = EvidenceAgent(MockLLMClient())
    cards: list[EvidenceCard] = []
    for source in sources:
        created = agent.extract(
            mission_id=MISSION_ID,
            source_id=uuid4(),
            source=source,
            mission_goal=mission_goal,
        )
        cards.append(
            EvidenceCard(
                id=uuid4(), created_at=datetime.now(UTC), **created.model_dump()
            )
        )
    return cards


def test_extracted_evidence_reaches_a_poc_candidate_offline() -> None:
    """Raw sources through real extraction must be able to reach a PoC.

    Before mock extraction scored relevance against the goal and quoted stated
    limitations, this path was impossible: every card scored zero relevance, so
    Phase C rejected every direction on evidence coverage.
    """

    goal = "Decide whether to adopt quantized on-device inference for robotics."
    sources = [
        SourceResult(
            source_type="arxiv",
            title="Quantized inference for on-device robotics",
            url="https://example.test/1",
            content=(
                "We evaluate 4-bit quantized transformer inference for on-device "
                "robotics control. Median latency reaches 38ms on the target "
                "controller. However, the evaluation covers only a single "
                "device class."
            ),
        ),
        SourceResult(
            source_type="arxiv",
            title="Accuracy cost of quantization in robotics models",
            url="https://example.test/2",
            content=(
                "Quantized robotics models lose 1.2% task accuracy relative to "
                "fp16. The study does not measure long-horizon manipulation."
            ),
        ),
    ]

    evidence = extracted_cards(sources, goal)
    assert all(card.relevance_score > 0 for card in evidence)
    assert all(card.limitation for card in evidence)

    handoff = PhaseCAnalysisStage(MockLLMClient()).analyze(
        mission_goal=goal, evidence=evidence, research_exhausted=False
    )

    assert handoff.status == "ready_for_poc"
    supplied = {card.id for card in evidence}
    for candidate in handoff.poc_candidates:
        assert set(candidate.evidence_ids) <= supplied


def test_sources_unrelated_to_the_goal_do_not_reach_a_poc() -> None:
    """Relevance must discriminate, not merely be non-zero."""

    goal = "Decide whether to adopt quantized on-device inference for robotics."
    sources = [
        SourceResult(
            source_type="arxiv",
            title="Medieval crop rotation",
            url="https://example.test/3",
            content=(
                "Manorial ledgers record three-field rotation in northern Europe. "
                "However, the surviving records cover only two counties."
            ),
        )
    ]

    evidence = extracted_cards(sources, goal)
    assert all(card.relevance_score == 0 for card in evidence)

    handoff = PhaseCAnalysisStage(MockLLMClient()).analyze(
        mission_goal=goal, evidence=evidence, research_exhausted=False
    )

    assert handoff.status != "ready_for_poc"
    assert handoff.poc_candidates == []
