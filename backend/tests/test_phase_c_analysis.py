"""Unit tests for deterministic Phase C analyst and critic behavior."""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.agents.analyst import AnalystAgent
from app.agents.critic import CriticAgent
from app.schemas.analysis import (
    AnalystOutcome,
    ClaimReview,
    CritiqueQuestionDraft,
    DirectionClaim,
    DirectionDraft,
    RankedDirection,
    SemanticQuestionScores,
)
from app.schemas.evidence_card import EvidenceCard
from app.services.scoring import (
    UnknownEvidenceReferenceError,
    direction_evidence_coverage,
    question_diversity,
)
from app.services.phase_c import build_phase_c_handoff, classify_claim_verdict


def evidence_card(
    *,
    mission_id: UUID,
    relevance: float,
    confidence: float,
    source_id: UUID | None = None,
) -> EvidenceCard:
    return EvidenceCard(
        id=uuid4(),
        mission_id=mission_id,
        source_id=source_id or uuid4(),
        relevance_score=relevance,
        extraction_confidence=confidence,
        created_at=datetime.now(UTC),
    )


class FixedDirectionGenerator:
    def __init__(self, drafts: Sequence[DirectionDraft]) -> None:
        self.drafts = drafts

    def generate_directions(
        self, *, mission_goal: str, evidence: Sequence[EvidenceCard]
    ) -> Sequence[DirectionDraft]:
        assert mission_goal
        assert evidence
        return self.drafts


class FixedQuestionGenerator:
    def __init__(self, questions: Sequence[CritiqueQuestionDraft]) -> None:
        self.questions = questions

    def generate_questions(
        self,
        *,
        mission_goal: str,
        directions: Sequence[RankedDirection],
        evidence: Sequence[EvidenceCard],
    ) -> Sequence[CritiqueQuestionDraft]:
        assert mission_goal
        assert directions
        assert evidence
        return self.questions


class ScoreByQuestionReviewer:
    def __init__(
        self, scores: dict[str, tuple[float, float]], default: tuple[float, float] = (0.9, 0.9)
    ) -> None:
        self.scores = scores
        self.default = default

    def review_question(
        self,
        *,
        question: CritiqueQuestionDraft,
        direction: RankedDirection,
        evidence: Sequence[EvidenceCard],
    ) -> SemanticQuestionScores:
        assert direction.id == question.direction_id
        assert evidence
        rationality, coverage = self.scores.get(question.id, self.default)
        return SemanticQuestionScores(
            rationality=rationality,
            viewpoint_coverage=coverage,
        )


def direction(
    identifier: str,
    title: str,
    evidence_ids: list[UUID],
    *,
    claim_id: str | None = None,
) -> DirectionDraft:
    return DirectionDraft(
        id=identifier,
        title=title,
        summary=f"Explore {title}.",
        claims=[
            DirectionClaim(
                id=claim_id or f"claim-{identifier}",
                statement=f"{title} can address the mission goal.",
                evidence_ids=evidence_ids,
            )
        ],
    )


def ranked_direction(draft: DirectionDraft) -> RankedDirection:
    return RankedDirection(
        **draft.model_dump(),
        evidence_coverage=0.8,
        rank=1,
    )


def question(
    identifier: str,
    *,
    direction_id: str,
    claim_id: str,
    text: str,
    evidence_ids: list[UUID],
    suggested_query: str | None = None,
) -> CritiqueQuestionDraft:
    return CritiqueQuestionDraft(
        id=identifier,
        direction_id=direction_id,
        challenged_claim_id=claim_id,
        question=text,
        rationale="The claim may omit a material limitation.",
        evidence_ids=evidence_ids,
        suggested_query=suggested_query,
    )


def test_direction_coverage_rewards_quality_and_independent_corroboration() -> None:
    mission_id = uuid4()
    source_one = uuid4()
    first = evidence_card(
        mission_id=mission_id,
        relevance=0.8,
        confidence=0.8,
        source_id=source_one,
    )
    same_source = evidence_card(
        mission_id=mission_id,
        relevance=0.9,
        confidence=0.5,
        source_id=source_one,
    )
    independent = evidence_card(
        mission_id=mission_id,
        relevance=0.7,
        confidence=0.8,
    )
    evidence_by_id = {
        card.id: card for card in (first, same_source, independent)
    }

    same_source_score = direction_evidence_coverage(
        direction("one", "Direction", [first.id, same_source.id]),
        evidence_by_id,
    )
    independent_score = direction_evidence_coverage(
        direction("two", "Direction", [first.id, independent.id]),
        evidence_by_id,
    )

    assert same_source_score == 0.64
    assert independent_score == 0.74


def test_unsupported_claim_receives_zero_not_a_negative_penalty() -> None:
    mission_id = uuid4()
    card = evidence_card(mission_id=mission_id, relevance=1, confidence=1)
    draft = DirectionDraft(
        id="direction",
        title="Grounded direction",
        summary="One supported and one unknown claim.",
        claims=[
            DirectionClaim(
                id="supported",
                statement="Supported.",
                evidence_ids=[card.id],
            ),
            DirectionClaim(id="unknown", statement="Unknown."),
        ],
    )

    assert direction_evidence_coverage(draft, {card.id: card}) == 0.5


def test_analyst_selects_at_most_four_and_retains_other_candidates() -> None:
    mission_id = uuid4()
    cards = [
        evidence_card(
            mission_id=mission_id,
            relevance=value,
            confidence=1,
        )
        for value in (0.95, 0.85, 0.75, 0.65, 0.55)
    ]
    drafts = [
        direction(f"d{index}", f"Direction {index}", [card.id])
        for index, card in enumerate(cards, start=1)
    ]

    outcome = AnalystAgent(FixedDirectionGenerator(drafts)).analyze(
        mission_goal="Find viable e-commerce extensions.",
        evidence=cards,
    )

    assert outcome.status == "ready"
    assert len(outcome.active_directions) == 4
    assert [item.id for item in outcome.active_directions] == ["d1", "d2", "d3", "d4"]
    assert [item.id for item in outcome.candidate_directions] == ["d5"]
    assert [item.rank for item in outcome.active_directions] == [1, 2, 3, 4]


def test_analyst_requests_research_when_no_grounded_direction_exists() -> None:
    mission_id = uuid4()
    card = evidence_card(mission_id=mission_id, relevance=0.9, confidence=0.9)
    unsupported = direction("d1", "Unsupported", [])

    outcome = AnalystAgent(FixedDirectionGenerator([unsupported])).analyze(
        mission_goal="Find a direction.",
        evidence=[card],
    )

    assert outcome.status == "research_required"
    assert not outcome.active_directions


def test_analyst_keeps_best_supported_version_of_duplicate_direction() -> None:
    mission_id = uuid4()
    weak = evidence_card(mission_id=mission_id, relevance=0.4, confidence=1)
    strong = evidence_card(mission_id=mission_id, relevance=0.9, confidence=1)
    drafts = [
        direction("weak", "Same Direction", [weak.id]),
        direction("strong", " same   direction ", [strong.id]),
    ]

    outcome = AnalystAgent(FixedDirectionGenerator(drafts)).analyze(
        mission_goal="Find a direction.",
        evidence=[weak, strong],
    )

    assert [item.id for item in outcome.active_directions] == ["strong"]
    assert outcome.active_directions[0].evidence_coverage == 0.9


def test_analyst_rejects_an_unknown_evidence_reference() -> None:
    mission_id = uuid4()
    card = evidence_card(mission_id=mission_id, relevance=0.9, confidence=0.9)
    draft = direction("d1", "Invalid", [uuid4()])

    with pytest.raises(UnknownEvidenceReferenceError):
        AnalystAgent(FixedDirectionGenerator([draft])).analyze(
            mission_goal="Find a direction.",
            evidence=[card],
        )


def test_question_diversity_detects_homogeneous_questions() -> None:
    original = "Does the experiment control for customer age?"

    assert question_diversity(original, []) == 1
    assert question_diversity(original, [original]) == 0
    assert question_diversity(
        "Is deployment latency measured?", [original]
    ) > 0.6


def test_critic_rejects_low_score_and_uses_next_candidate_as_replacement() -> None:
    mission_id = uuid4()
    card = evidence_card(mission_id=mission_id, relevance=0.9, confidence=0.9)
    draft = direction("d1", "Conversational commerce", [card.id], claim_id="c1")
    analysis = AnalystOutcome(
        status="ready",
        active_directions=[ranked_direction(draft)],
    )
    questions = [
        question(
            "q1",
            direction_id="d1",
            claim_id="c1",
            text="Does the experiment control for customer age?",
            evidence_ids=[card.id],
            suggested_query="customer age conversational commerce experiment",
        ),
        question(
            "q2",
            direction_id="d1",
            claim_id="c1",
            text="Could deployment violate regional privacy regulation?",
            evidence_ids=[card.id],
        ),
        question(
            "q3",
            direction_id="d1",
            claim_id="c1",
            text="Is recommendation latency measured under production load?",
            evidence_ids=[],
            suggested_query="conversational commerce recommendation latency",
        ),
    ]
    reviewer = ScoreByQuestionReviewer({"q2": (0.2, 0.9)})
    critic = CriticAgent(
        FixedQuestionGenerator(questions),
        reviewer,
        max_questions=2,
    )

    outcome = critic.critique(
        mission_goal="Evaluate conversational commerce.",
        analysis=analysis,
        evidence=[card],
    )

    assert [item.question.id for item in outcome.accepted_questions] == ["q1", "q3"]
    assert [item.question.id for item in outcome.rejected_questions] == ["q2"]
    assert outcome.rejected_questions[0].rejection_reasons == ["low_rationality"]
    assert outcome.status == "research_required"
    assert outcome.research_request is not None
    assert outcome.research_request.queries == [
        "customer age conversational commerce experiment",
        "conversational commerce recommendation latency",
    ]


def test_critic_rejects_a_homogeneous_question() -> None:
    mission_id = uuid4()
    card = evidence_card(mission_id=mission_id, relevance=0.9, confidence=0.9)
    draft = direction("d1", "Direction", [card.id], claim_id="c1")
    analysis = AnalystOutcome(
        status="ready",
        active_directions=[ranked_direction(draft)],
    )
    duplicate_text = "Does the evidence control the same important variable?"
    questions = [
        question(
            "q1",
            direction_id="d1",
            claim_id="c1",
            text=duplicate_text,
            evidence_ids=[card.id],
        ),
        question(
            "q2",
            direction_id="d1",
            claim_id="c1",
            text=duplicate_text,
            evidence_ids=[card.id],
        ),
    ]

    outcome = CriticAgent(
        FixedQuestionGenerator(questions),
        ScoreByQuestionReviewer({}),
    ).critique(
        mission_goal="Evaluate the direction.",
        analysis=analysis,
        evidence=[card],
    )

    assert [item.question.id for item in outcome.accepted_questions] == ["q1"]
    assert outcome.rejected_questions[0].rejection_reasons == ["low_diversity"]
    assert outcome.status == "ready"


def test_all_rejected_questions_end_phase_c_with_targeted_research() -> None:
    mission_id = uuid4()
    card = evidence_card(mission_id=mission_id, relevance=0.9, confidence=0.9)
    draft = DirectionDraft(
        id="d1",
        title="Conversational commerce",
        summary="Explore a shopping assistant.",
        claims=[
            DirectionClaim(
                id="supported",
                statement="It improves recommendation relevance.",
                evidence_ids=[card.id],
            ),
            DirectionClaim(
                id="unknown",
                statement="It improves purchase conversion.",
            ),
        ],
    )
    analysis = AnalystOutcome(
        status="ready",
        active_directions=[ranked_direction(draft)],
    )
    weak_question = question(
        "q1",
        direction_id="d1",
        claim_id="supported",
        text="Is this good?",
        evidence_ids=[],
    )

    outcome = CriticAgent(
        FixedQuestionGenerator([weak_question]),
        ScoreByQuestionReviewer({"q1": (0.1, 0.1)}),
    ).critique(
        mission_goal="Evaluate conversational commerce.",
        analysis=analysis,
        evidence=[card],
    )

    assert outcome.status == "research_required"
    assert not outcome.accepted_questions
    assert outcome.research_request is not None
    assert outcome.research_request.direction_ids == ["d1"]
    assert outcome.research_request.claim_ids == ["unknown"]
    assert "It improves purchase conversion." in outcome.research_request.queries[0]


def test_phase_c_hands_evidence_grounded_poc_candidate_to_d() -> None:
    mission_id = uuid4()
    card = evidence_card(mission_id=mission_id, relevance=0.9, confidence=0.9)
    draft = direction("d1", "Hybrid recommender", [card.id], claim_id="c1")
    analysis = AnalystOutcome(
        status="ready",
        active_directions=[ranked_direction(draft)],
    )
    critique_question = question(
        "q1",
        direction_id="d1",
        claim_id="c1",
        text="Does the cited comparison use a representative baseline?",
        evidence_ids=[card.id],
    )
    critique = CriticAgent(
        FixedQuestionGenerator([critique_question]),
        ScoreByQuestionReviewer({}),
    ).critique(
        mission_goal="Evaluate conversational commerce.",
        analysis=analysis,
        evidence=[card],
    )

    handoff = build_phase_c_handoff(
        mission_goal="Evaluate conversational commerce.",
        analysis=analysis,
        critique=critique,
        evidence=[card],
        claim_reviews=[
            ClaimReview(
                direction_id="d1",
                claim_id="c1",
                poc_testability=0.9,
                rationale="The core hypothesis can be measured in an offline test.",
            )
        ],
    )

    assert handoff.status == "ready_for_poc"
    assert handoff.poc_candidates[0].direction_id == "d1"
    assert handoff.poc_candidates[0].evidence_ids == [card.id]
    assert handoff.poc_candidates[0].unresolved_questions == [
        "Does the cited comparison use a representative baseline?"
    ]


def test_phase_c_requests_research_then_reports_no_viable_direction_when_exhausted() -> None:
    mission_id = uuid4()
    card = evidence_card(mission_id=mission_id, relevance=0.9, confidence=0.9)
    draft = direction("d1", "Hybrid recommender", [card.id], claim_id="c1")
    analysis = AnalystOutcome(
        status="ready",
        active_directions=[ranked_direction(draft)],
    )
    critique_question = question(
        "q1",
        direction_id="d1",
        claim_id="c1",
        text="Does the result generalize to real e-commerce traffic?",
        evidence_ids=[card.id],
        suggested_query="hybrid recommender production ecommerce evaluation",
    )
    critique = CriticAgent(
        FixedQuestionGenerator([critique_question]),
        ScoreByQuestionReviewer({}),
    ).critique(
        mission_goal="Evaluate conversational commerce.",
        analysis=analysis,
        evidence=[card],
    )

    retry_handoff = build_phase_c_handoff(
        mission_goal="Evaluate conversational commerce.",
        analysis=analysis,
        critique=critique,
        evidence=[card],
        claim_reviews=[],
    )
    final_handoff = build_phase_c_handoff(
        mission_goal="Evaluate conversational commerce.",
        analysis=analysis,
        critique=critique,
        evidence=[card],
        claim_reviews=[],
        research_exhausted=True,
    )

    assert retry_handoff.status == "research_required"
    assert retry_handoff.research_request == critique.research_request
    assert final_handoff.status == "no_viable_direction"
    assert not final_handoff.poc_candidates


def test_missing_counterevidence_review_is_unknown_not_negative() -> None:
    assert classify_claim_verdict(
        support_strength=0.8,
        counterevidence_strength=None,
    ) == "unknown"


def test_strong_counterevidence_refutes_a_weakly_supported_claim() -> None:
    assert classify_claim_verdict(
        support_strength=0.3,
        counterevidence_strength=0.8,
    ) == "refuted"


def test_contested_but_testable_claim_can_still_become_a_poc() -> None:
    mission_id = uuid4()
    supporting = evidence_card(
        mission_id=mission_id,
        relevance=0.9,
        confidence=0.9,
    )
    opposing = evidence_card(
        mission_id=mission_id,
        relevance=0.8,
        confidence=0.8,
    )
    draft = direction(
        "d1",
        "Hybrid recommender",
        [supporting.id],
        claim_id="c1",
    )
    analysis = AnalystOutcome(
        status="ready",
        active_directions=[ranked_direction(draft)],
    )
    critique_question = question(
        "q1",
        direction_id="d1",
        claim_id="c1",
        text="Do results differ across product categories?",
        evidence_ids=[opposing.id],
    )
    critique = CriticAgent(
        FixedQuestionGenerator([critique_question]),
        ScoreByQuestionReviewer({}),
    ).critique(
        mission_goal="Evaluate conversational commerce.",
        analysis=analysis,
        evidence=[supporting, opposing],
    )

    handoff = build_phase_c_handoff(
        mission_goal="Evaluate conversational commerce.",
        analysis=analysis,
        critique=critique,
        evidence=[supporting, opposing],
        claim_reviews=[
            ClaimReview(
                direction_id="d1",
                claim_id="c1",
                opposing_evidence_ids=[opposing.id],
                poc_testability=0.9,
                rationale="Evidence conflicts, but an A/B test can resolve it.",
            )
        ],
    )

    assert handoff.status == "ready_for_poc"
    assert handoff.claim_assessments[0].verdict == "contested"


def test_no_poc_only_after_new_evidence_remains_insufficient() -> None:
    mission_id = uuid4()
    weak_support = evidence_card(
        mission_id=mission_id,
        relevance=0.4,
        confidence=0.5,
    )
    draft = direction(
        "d1",
        "Unproven direction",
        [weak_support.id],
        claim_id="c1",
    )
    analysis = AnalystOutcome(
        status="ready",
        active_directions=[ranked_direction(draft)],
    )
    critique_question = question(
        "q1",
        direction_id="d1",
        claim_id="c1",
        text="Can the central outcome be measured in the available environment?",
        evidence_ids=[],
    )
    critique = CriticAgent(
        FixedQuestionGenerator([critique_question]),
        ScoreByQuestionReviewer({}),
    ).critique(
        mission_goal="Evaluate an extension.",
        analysis=analysis,
        evidence=[weak_support],
    )
    reviews = [
        ClaimReview(
            direction_id="d1",
            claim_id="c1",
            poc_testability=0.8,
            rationale="The hypothesis is testable but still lacks minimum support.",
        )
    ]

    before_limit = build_phase_c_handoff(
        mission_goal="Evaluate an extension.",
        analysis=analysis,
        critique=critique,
        evidence=[weak_support],
        claim_reviews=reviews,
    )
    after_limit = build_phase_c_handoff(
        mission_goal="Evaluate an extension.",
        analysis=analysis,
        critique=critique,
        evidence=[weak_support],
        claim_reviews=reviews,
        research_exhausted=True,
    )

    assert before_limit.status == "research_required"
    assert before_limit.claim_assessments[0].verdict == "unknown"
    assert after_limit.status == "no_viable_direction"
    assert "Added evidence remained insufficient" in after_limit.reason
