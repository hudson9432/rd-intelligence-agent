"""Scoring candidates and recommending one.

Phase C asks whether a direction can be settled by experiment; this asks
whether it is worth settling. The gap it fills is real: nothing earlier checks
whether a direction answers the mission's question at all, because the Analyst
ranks on evidence coverage and breaks ties on title. A well-evidenced but
tangential direction wins by default.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.agents.decision import DecisionAgent, DecisionScoringError, recommend
from app.agents.orchestrator import WorkflowStageError
from app.core.llm import LLMClient, MockLLMClient
from app.repositories.technology_opportunity import TechnologyOpportunityRepository
from app.schemas.analysis import EvaluatedClaim, PhaseCHandoff, PocCandidate
from app.schemas.evidence_card import EvidenceCard
from app.schemas.llm import LLMCompletion, LLMMessage
from app.schemas.research_mission import ResearchMissionCreate
from app.services.decision_stage import OpportunityDecisionStage
from app.services.mission import MissionService

GOAL = "Decide whether quantized on-device inference suits our robotics line."


class RatingClient(LLMClient):
    """Returns fixed ratings, cycling if several candidates are scored."""

    model_name = "rating"

    def __init__(self, *bodies: str) -> None:
        self._bodies = list(bodies)
        self.calls = 0

    def complete(self, messages: list[LLMMessage]) -> LLMCompletion:
        del messages
        body = self._bodies[min(self.calls, len(self._bodies) - 1)]
        self.calls += 1
        return LLMCompletion(content=body, model="rating", mocked=False)


def rating(*, align=4, maturity=4, novelty=3, difficulty=2) -> str:
    return (
        f'{{"goal_alignment":{align},"technical_maturity":{maturity},'
        f'"novelty":{novelty},"implementation_difficulty":{difficulty},'
        '"rationale":"Grounded in the supplied evidence."}'
    )


def evidence_card(mission_id: UUID) -> EvidenceCard:
    return EvidenceCard(
        id=uuid4(),
        mission_id=mission_id,
        source_id=uuid4(),
        relevance_score=0.9,
        extraction_confidence=0.9,
        created_at=datetime.now(UTC),
    )


def persisted_evidence(session: Session, mission_id: UUID) -> EvidenceCard:
    """Store a source and a card, which the opportunity record must reference."""

    from app.repositories.evidence_card import EvidenceCardRepository
    from app.repositories.source_document import SourceDocumentRepository
    from app.schemas.evidence_card import EvidenceCardCreate
    from app.schemas.source_document import SourceDocumentCreate

    source = SourceDocumentRepository(session).save(
        SourceDocumentCreate(
            mission_id=mission_id,
            source_type="arxiv",
            title="Quantized inference on device",
            url=f"https://example.test/{mission_id}",
            content_hash="b" * 64,
        )
    )
    stored = EvidenceCardRepository(session).save(
        EvidenceCardCreate(
            mission_id=mission_id,
            source_id=UUID(source.id),
            relevance_score=0.9,
            extraction_confidence=0.9,
        )
    )
    return EvidenceCard.model_validate(stored)


def candidate(direction_id: str, card: EvidenceCard) -> PocCandidate:
    return PocCandidate(
        direction_id=direction_id,
        title=f"Direction {direction_id}",
        hypothesis="A 4-bit model meets the latency budget.",
        evidence_ids=[card.id],
        evidence_coverage=0.8,
        claim_assessments=[
            EvaluatedClaim(
                direction_id=direction_id,
                claim_id=f"claim-{direction_id}",
                statement="Latency stays under 50ms.",
                is_core=True,
                supporting_evidence_ids=[card.id],
                support_strength=0.8,
                poc_testability=0.9,
                verdict="supported",
                resolution_status="resolved",
                rationale="Measurable within a bounded PoC.",
            )
        ],
    )


def handoff_of(*candidates: PocCandidate) -> PhaseCHandoff:
    return PhaseCHandoff(
        status="ready_for_poc",
        reason="A direction is testable.",
        poc_candidates=list(candidates),
    )


def score_with(client: LLMClient, *direction_ids: str):
    mission_id = uuid4()
    card = evidence_card(mission_id)
    candidates = [candidate(item, card) for item in direction_ids]
    return DecisionAgent(client).score(
        mission_id=mission_id,
        mission_goal=GOAL,
        handoff=handoff_of(*candidates),
        evidence=[card],
    )


# ------------------------------------------------------------------- agent


def test_every_candidate_is_scored_not_only_the_winner() -> None:
    """A reader who cannot see why the others lost cannot disagree."""

    scored = score_with(RatingClient(rating()), "d1", "d2", "d3")

    assert len(scored) == 3


def test_candidates_are_returned_best_first() -> None:
    client = RatingClient(rating(align=2, maturity=2), rating(align=5, maturity=5))

    scored = score_with(client, "weak", "strong")

    assert [item.candidate.direction_id for item in scored] == ["strong", "weak"]
    assert scored[0].opportunity.overall_score > scored[1].opportunity.overall_score


def test_the_derived_dimensions_are_not_taken_from_the_model() -> None:
    """Evidence strength and feasibility come from what Phase C established."""

    scored = score_with(RatingClient(rating()), "d1")
    opportunity = scored[0].opportunity

    # 0.8 coverage with full agreement maps onto 4; 0.9 testability onto 5.
    assert opportunity.evidence_strength == 4
    assert opportunity.poc_feasibility == 5


def test_the_opportunity_cites_only_evidence_the_candidate_cites() -> None:
    scored = score_with(RatingClient(rating()), "d1")

    assert (
        scored[0].opportunity.related_evidence_ids_json
        == scored[0].candidate.evidence_ids
    )


def test_an_unusable_rating_fails_rather_than_scoring_anyway() -> None:
    with pytest.raises(DecisionScoringError, match="opportunity-rating contract"):
        score_with(RatingClient("not json"), "d1")


def test_the_offline_rating_holds_ungroundable_dimensions_at_the_middle() -> None:
    """The mock must not look better informed than it is."""

    scored = score_with(MockLLMClient(), "d1")
    opportunity = scored[0].opportunity

    assert opportunity.goal_alignment == 3
    assert opportunity.implementation_difficulty == 3
    assert "nothing to judge them by" in opportunity.rationale


# ------------------------------------------------------------ recommendation


def test_the_recommendation_follows_the_ranking() -> None:
    client = RatingClient(rating(align=2, maturity=2), rating(align=5, maturity=5))

    decision = recommend(score_with(client, "weak", "strong"))

    assert decision.recommendation == "proceed_with_poc"
    assert decision.selected_direction_id == "strong"


def test_the_rationale_shows_what_the_alternatives_scored() -> None:
    client = RatingClient(rating(align=5, maturity=5), rating(align=2, maturity=2))

    decision = recommend(score_with(client, "chosen", "other"))

    assert "Ranked above" in decision.rationale


def test_nothing_to_score_is_a_no_go() -> None:
    decision = recommend([])

    assert decision.recommendation == "do_not_proceed"
    assert decision.selected_direction_id is None


# -------------------------------------------------------------------- stage


def test_the_stage_stores_every_candidate_it_scored(session: Session) -> None:
    mission = MissionService(session).create(
        ResearchMissionCreate(title="Edge", goal=GOAL)
    )
    mission_id = UUID(mission.id)
    card = persisted_evidence(session, mission_id)
    candidates = [candidate("d1", card), candidate("d2", card)]

    stage = OpportunityDecisionStage(session, MockLLMClient())
    decision = stage.decide(
        mission_goal=GOAL, handoff=handoff_of(*candidates), evidence=[card]
    )

    stored = TechnologyOpportunityRepository(session).list_for_mission(mission_id)
    assert len(stored) == 2, "every candidate is recorded, not only the winner"
    assert decision.selected_direction_id in {"d1", "d2"}


def test_a_handoff_with_no_candidate_is_a_no_go(session: Session) -> None:
    stage = OpportunityDecisionStage(session, MockLLMClient())

    decision = stage.decide(
        mission_goal=GOAL,
        handoff=PhaseCHandoff(
            status="no_viable_direction", reason="Nothing survived the gate."
        ),
        evidence=[],
    )

    assert decision.recommendation == "do_not_proceed"


def test_scoring_without_evidence_fails_rather_than_guessing(
    session: Session,
) -> None:
    stage = OpportunityDecisionStage(session, MockLLMClient())
    card = evidence_card(uuid4())

    with pytest.raises(WorkflowStageError, match="needs evidence"):
        stage.decide(
            mission_goal=GOAL,
            handoff=handoff_of(candidate("d1", card)),
            evidence=[],
        )
