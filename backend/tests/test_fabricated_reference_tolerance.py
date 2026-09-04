"""A model that invents a reference must lose that item, not the mission.

Every generator in Phase C is a language model, and language models fabricate
identifiers. Before these guards, one invented UUID anywhere in the analysis
raised out of the workflow's Analysis node and failed the whole run — after the
sources had been fetched and every evidence card extracted and stored. A live
run against a real provider lost 26 evidence cards and six minutes that way.

The references are still rejected. What changed is the blast radius.
"""

from uuid import UUID, uuid4

from app.agents.analyst import AnalystAgent
from app.agents.critic import CriticAgent
from app.schemas.analysis import (
    ClaimReview,
    CritiqueQuestionDraft,
    DirectionClaim,
    DirectionDraft,
    SemanticQuestionScores,
)
from app.schemas.evidence_card import EvidenceCard
from app.services.phase_c import build_phase_c_handoff

from tests.test_phase_c_analysis import evidence_card

GOAL = "Find a feasible direction."


class FixedDirections:
    def __init__(self, drafts: list[DirectionDraft]) -> None:
        self.drafts = drafts

    def generate_directions(self, *, mission_goal: str, evidence):
        del mission_goal, evidence
        return self.drafts


class FixedQuestions:
    def __init__(self, questions: list[CritiqueQuestionDraft]) -> None:
        self.questions = questions

    def generate_questions(self, *, mission_goal: str, directions, evidence):
        del mission_goal, directions, evidence
        return self.questions


class AcceptingReviewer:
    def review_question(self, *, question, direction, evidence):
        del question, direction, evidence
        return SemanticQuestionScores(rationality=0.9, viewpoint_coverage=0.9)


def draft(direction_id: str, evidence_ids: list[UUID]) -> DirectionDraft:
    return DirectionDraft(
        id=direction_id,
        title=f"Direction {direction_id}",
        summary="A proposed direction.",
        claims=[
            DirectionClaim(
                id=f"claim-{direction_id}",
                statement=f"Claim for {direction_id}.",
                evidence_ids=evidence_ids,
                is_core=True,
            )
        ],
    )


def question(
    question_id: str, direction_id: str, evidence_ids: list[UUID]
) -> CritiqueQuestionDraft:
    return CritiqueQuestionDraft(
        id=question_id,
        direction_id=direction_id,
        challenged_claim_id=f"claim-{direction_id}",
        question=f"Is the {question_id} claim boundary tested by the evidence?",
        rationale="The cited evidence does not record a boundary condition.",
        evidence_ids=evidence_ids,
    )


def analysis_with(card: EvidenceCard, *direction_ids: str):
    drafts = [draft(direction_id, [card.id]) for direction_id in direction_ids]
    return AnalystAgent(FixedDirections(drafts)).analyze(
        mission_goal=GOAL, evidence=[card]
    )


# ------------------------------------------------------------------- critic


def test_critic_discards_a_question_citing_unknown_evidence() -> None:
    card = evidence_card(mission_id=uuid4(), relevance=0.9, confidence=0.9)
    analysis = analysis_with(card, "d1", "d2")
    critic = CriticAgent(
        FixedQuestions(
            [
                question("fabricated", "d1", [uuid4()]),
                question("grounded", "d2", [card.id]),
            ]
        ),
        AcceptingReviewer(),
    )

    outcome = critic.critique(mission_goal=GOAL, analysis=analysis, evidence=[card])

    accepted = [item.question.id for item in outcome.accepted_questions]
    assert "fabricated" not in accepted
    assert "grounded" in accepted
    # An unusable question is not a quality rejection, so it records no score.
    assert [item.question.id for item in outcome.rejected_questions] == []


def test_critic_discards_a_question_aimed_at_an_inactive_direction() -> None:
    card = evidence_card(mission_id=uuid4(), relevance=0.9, confidence=0.9)
    analysis = analysis_with(card, "d1")
    critic = CriticAgent(
        FixedQuestions(
            [
                question("orphan", "does-not-exist", [card.id]),
                question("grounded", "d1", [card.id]),
            ]
        ),
        AcceptingReviewer(),
    )

    outcome = critic.critique(mission_goal=GOAL, analysis=analysis, evidence=[card])

    assert [item.question.id for item in outcome.accepted_questions] == ["grounded"]


# ------------------------------------------------------------------ phase C


def handoff_with(card: EvidenceCard, reviews: list[ClaimReview]):
    analysis = analysis_with(card, "d1")
    critic = CriticAgent(
        FixedQuestions([question("q1", "d1", [card.id])]), AcceptingReviewer()
    )
    critique = critic.critique(mission_goal=GOAL, analysis=analysis, evidence=[card])
    return build_phase_c_handoff(
        mission_goal=GOAL,
        analysis=analysis,
        critique=critique,
        evidence=[card],
        claim_reviews=reviews,
        research_exhausted=True,
    )


def review(**overrides) -> ClaimReview:
    defaults = {
        "direction_id": "d1",
        "claim_id": "claim-d1",
        "opposing_evidence_ids": [],
        "poc_testability": 0.8,
        "rationale": "The claim is measurable within a bounded PoC.",
    }
    defaults.update(overrides)
    return ClaimReview(**defaults)


def assert_claim_is_unknown(handoff) -> None:
    """A discarded review must leave the claim unjudged, never opposed."""

    claims = handoff.claim_assessments or [
        assessment
        for candidate in handoff.poc_candidates
        for assessment in candidate.claim_assessments
    ]
    assert claims
    for assessment in claims:
        assert assessment.opposing_evidence_ids == []
        assert assessment.verdict != "refuted"


def test_a_review_citing_unknown_opposing_evidence_is_treated_as_missing() -> None:
    card = evidence_card(mission_id=uuid4(), relevance=0.9, confidence=0.9)

    handoff = handoff_with(card, [review(opposing_evidence_ids=[uuid4()])])

    assert handoff.status in {"ready_for_poc", "no_viable_direction"}
    assert_claim_is_unknown(handoff)


def test_a_review_opposing_its_own_support_is_treated_as_missing() -> None:
    """Invariant 3: a self-contradicting review is unknown, not counterevidence."""

    card = evidence_card(mission_id=uuid4(), relevance=0.9, confidence=0.9)

    handoff = handoff_with(card, [review(opposing_evidence_ids=[card.id])])

    assert_claim_is_unknown(handoff)


def test_a_review_of_a_claim_not_under_analysis_is_dropped() -> None:
    card = evidence_card(mission_id=uuid4(), relevance=0.9, confidence=0.9)

    handoff = handoff_with(card, [review(direction_id="ghost", claim_id="claim-ghost")])

    assert_claim_is_unknown(handoff)


def test_duplicate_reviews_for_one_claim_do_not_raise() -> None:
    card = evidence_card(mission_id=uuid4(), relevance=0.9, confidence=0.9)

    handoff = handoff_with(card, [review(), review(poc_testability=0.1)])

    assert handoff.status in {"ready_for_poc", "no_viable_direction"}
