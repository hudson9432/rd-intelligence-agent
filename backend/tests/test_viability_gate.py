"""The viability gate must judge the evidence once research is exhausted.

A live provider never reached `ready_for_poc`, whatever the evidence. The gate
short-circuited on `critique.status == "research_required"`, and a real critic
attaches a suggested search to nearly every accepted question, so the critique
stays `research_required` forever — a good critic always has another question.
Claim evaluation therefore never ran: three search rounds and twenty-nine
evidence cards ended at `no_viable_direction` without a single claim verdict.

`docs/PHASE_C_CONTRACT.md` reserves that state for "the research budget is
exhausted **and** no direction satisfies the core-claim viability rules". These
tests hold the gate to the second half of that sentence.

The deterministic mock hid this: its question generator omits a suggested
search whenever an evidence card records a limitation, which is an artefact of
the mock rather than of the design.
"""

from collections.abc import Sequence
from uuid import UUID, uuid4

from app.agents.analyst import AnalystAgent
from app.agents.critic import CriticAgent
from app.schemas.analysis import (
    ClaimReview,
    CritiqueQuestionDraft,
    DirectionClaim,
    DirectionDraft,
)
from app.schemas.evidence_card import EvidenceCard
from app.services.phase_c import build_phase_c_handoff
from tests.test_phase_c_analysis import (
    FixedDirectionGenerator,
    FixedQuestionGenerator,
    ScoreByQuestionReviewer,
    evidence_card,
)


def accepting_reviewer() -> ScoreByQuestionReviewer:
    """Every question passes review, so only the gate under test can fail."""

    return ScoreByQuestionReviewer({})


GOAL = "Decide whether the approach is worth a proof of concept."


def strong_evidence(mission_id: UUID, count: int = 2) -> list[EvidenceCard]:
    """Independent, well-scored cards, so support strength clears the bar."""

    return [
        evidence_card(mission_id=mission_id, relevance=0.9, confidence=0.9)
        for _ in range(count)
    ]


def direction_citing(evidence: Sequence[EvidenceCard]) -> DirectionDraft:
    return DirectionDraft(
        id="d1",
        title="Quantized on-device inference",
        summary="A testable direction.",
        claims=[
            DirectionClaim(
                id="c1",
                statement="The quantized model meets the latency budget.",
                evidence_ids=[card.id for card in evidence],
                is_core=True,
            )
        ],
    )


def question_with_suggestion(evidence: Sequence[EvidenceCard]):
    """What a live critic produces: a fair question plus a follow-up search."""

    return CritiqueQuestionDraft(
        id="q1",
        direction_id="d1",
        challenged_claim_id="c1",
        question="Does the latency hold on a second device class?",
        rationale="The cited evidence measures one device class.",
        evidence_ids=[card.id for card in evidence],
        suggested_query="quantized inference latency across device classes",
    )


def poc_testable_review() -> ClaimReview:
    return ClaimReview(
        direction_id="d1",
        claim_id="c1",
        opposing_evidence_ids=[],
        poc_testability=0.9,
        rationale="Latency is directly measurable in a bounded PoC.",
    )


def gate(
    evidence: Sequence[EvidenceCard],
    *,
    research_exhausted: bool,
    reviews: Sequence[ClaimReview],
    evidence_pool: Sequence[EvidenceCard] | None = None,
):
    """Run the gate over a direction citing `evidence`.

    `evidence_pool` widens the set Phase C is given without widening what the
    direction cites, which is how opposing evidence reaches a claim review.
    """

    pool = list(evidence_pool if evidence_pool is not None else evidence)
    analysis = AnalystAgent(
        FixedDirectionGenerator([direction_citing(evidence)])
    ).analyze(mission_goal=GOAL, evidence=pool)
    critique = CriticAgent(
        FixedQuestionGenerator([question_with_suggestion(evidence)]),
        accepting_reviewer(),
    ).critique(mission_goal=GOAL, analysis=analysis, evidence=pool)

    # The precondition this whole file is about.
    assert critique.status == "research_required"

    return build_phase_c_handoff(
        mission_goal=GOAL,
        analysis=analysis,
        critique=critique,
        evidence=pool,
        claim_reviews=list(reviews),
        research_exhausted=research_exhausted,
    )


def test_outstanding_questions_still_ask_for_research_while_budget_remains() -> None:
    """Unchanged behaviour: with budget left, the critique gets its re-search."""

    evidence = strong_evidence(uuid4())

    handoff = gate(evidence, research_exhausted=False, reviews=[poc_testable_review()])

    assert handoff.status == "research_required"
    assert handoff.research_request is not None


def test_a_supported_testable_claim_reaches_poc_once_research_is_exhausted() -> None:
    """The case a live run could never reach before."""

    mission_id = uuid4()
    evidence = strong_evidence(mission_id)

    handoff = gate(evidence, research_exhausted=True, reviews=[poc_testable_review()])

    assert handoff.status == "ready_for_poc", handoff.reason
    assert handoff.poc_candidates
    candidate = handoff.poc_candidates[0]
    assert set(candidate.evidence_ids) <= {card.id for card in evidence}
    assert [item.verdict for item in candidate.claim_assessments] == ["supported"]


def test_the_outstanding_question_is_carried_into_the_candidate() -> None:
    """A question the critic never got to resolve becomes a PoC unknown."""

    evidence = strong_evidence(uuid4())

    handoff = gate(evidence, research_exhausted=True, reviews=[poc_testable_review()])

    candidate = handoff.poc_candidates[0]
    assert candidate.unresolved_questions


def test_an_untestable_claim_still_reports_no_viable_direction() -> None:
    """Falling through must not turn the gate into a rubber stamp."""

    evidence = strong_evidence(uuid4())
    untestable = ClaimReview(
        direction_id="d1",
        claim_id="c1",
        opposing_evidence_ids=[],
        poc_testability=0.1,
        rationale="No bounded experiment could settle this claim.",
    )

    handoff = gate(evidence, research_exhausted=True, reviews=[untestable])

    assert handoff.status == "no_viable_direction"
    assert handoff.poc_candidates == []


def test_a_refuted_claim_still_reports_no_viable_direction() -> None:
    """Falling through must respect the refuted rule, not bypass it.

    Refuted needs counterevidence at or above 0.7 that also exceeds support by
    0.15, so the claim is built with modest support and two strong independent
    opposing cards.
    """

    mission_id = uuid4()
    supporting = [evidence_card(mission_id=mission_id, relevance=0.7, confidence=0.7)]
    opposing = [
        evidence_card(mission_id=mission_id, relevance=0.9, confidence=0.9)
        for _ in range(2)
    ]
    all_evidence = [*supporting, *opposing]

    handoff = gate(
        supporting,
        research_exhausted=True,
        reviews=[
            ClaimReview(
                direction_id="d1",
                claim_id="c1",
                opposing_evidence_ids=[card.id for card in opposing],
                poc_testability=0.9,
                rationale="Independent measurements contradict the claim.",
            )
        ],
        evidence_pool=all_evidence,
    )

    assert [item.verdict for item in handoff.claim_assessments] == ["refuted"]
    assert handoff.status == "no_viable_direction"
    assert handoff.poc_candidates == []


def test_no_claim_review_leaves_the_claim_unknown_and_unviable() -> None:
    """Invariant 3: absent review stays unknown, never becomes a PoC."""

    evidence = strong_evidence(uuid4())

    handoff = gate(evidence, research_exhausted=True, reviews=[])

    assert handoff.status == "no_viable_direction"
    assert [item.verdict for item in handoff.claim_assessments] == ["unknown"]


def test_an_empty_analysis_still_reports_no_viable_direction() -> None:
    """Nothing to judge means the gate must not fall through to a candidate."""

    evidence = strong_evidence(uuid4())
    analysis = AnalystAgent(FixedDirectionGenerator([])).analyze(
        mission_goal=GOAL, evidence=evidence
    )
    critique = CriticAgent(FixedQuestionGenerator([]), accepting_reviewer()).critique(
        mission_goal=GOAL, analysis=analysis, evidence=evidence
    )

    handoff = build_phase_c_handoff(
        mission_goal=GOAL,
        analysis=analysis,
        critique=critique,
        evidence=evidence,
        claim_reviews=[],
        research_exhausted=True,
    )

    assert handoff.status == "no_viable_direction"
    assert handoff.poc_candidates == []
