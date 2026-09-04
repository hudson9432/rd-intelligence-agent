"""Search and Evidence stages, and the mission they now complete."""

from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.llm import MockLLMClient
from app.repositories.evidence_card import EvidenceCardRepository
from app.repositories.source_document import SourceDocumentRepository
from app.schemas.research_mission import MissionStatus, ResearchMissionCreate
from app.schemas.source_result import SourceResult
from app.services.evidence_stage import PersistingEvidenceStage
from app.services.mission import MissionService
from app.services.search_stage import ResearchSourceSearchStage
from app.services.workflow import WorkflowService

GOAL = "Decide whether retrieval augmented generation is reliable enough for our product."


def mock_settings() -> Settings:
    return Settings(mock_external_apis=True, demo_mode=False)


def search_stage() -> ResearchSourceSearchStage:
    return ResearchSourceSearchStage(settings=mock_settings())


def evidence_stage(session: Session) -> PersistingEvidenceStage:
    return PersistingEvidenceStage(session, llm_client=MockLLMClient())


def create_mission(session: Session) -> UUID:
    mission = MissionService(session).create(
        ResearchMissionCreate(title="RAG reliability", goal=GOAL)
    )
    return UUID(mission.id)


def source(title: str, url: str) -> SourceResult:
    return SourceResult(
        source_type="arxiv",
        title=title,
        url=url,
        content=(
            "The method improves grounded answer quality. However, the "
            "evaluation covers only one corpus."
        ),
    )


# ------------------------------------------------------------------- search


def test_search_returns_sources_for_the_supplied_queries() -> None:
    results = search_stage().search(goal=GOAL, queries=[GOAL], iteration=0)

    assert results
    assert {result.source_type for result in results} == {"arxiv", "github"}


def test_search_does_not_return_a_source_twice_across_rounds() -> None:
    """A re-search round must add evidence, not re-extract what is held."""

    stage = search_stage()

    first = stage.search(goal=GOAL, queries=[GOAL], iteration=0)
    second = stage.search(goal=GOAL, queries=[GOAL], iteration=1)

    assert first
    # Mock replay ignores the query, so round two is entirely a repeat. That
    # is the documented offline limitation, and the stage must absorb it.
    assert second == []


def test_each_stage_instance_starts_with_no_memory() -> None:
    """Seen-source memory must not leak between missions."""

    first = search_stage().search(goal=GOAL, queries=[GOAL], iteration=0)
    second = search_stage().search(goal=GOAL, queries=[GOAL], iteration=0)

    assert first == second


# ----------------------------------------------------------------- evidence


def test_extraction_persists_the_source_and_the_evidence(session: Session) -> None:
    mission_id = create_mission(session)
    sources = [source("Grounded retrieval", "https://example.test/a")]

    cards = evidence_stage(session).extract(
        mission_id=mission_id, goal=GOAL, sources=sources
    )

    assert len(cards) == 1
    stored_sources = SourceDocumentRepository(session).list_for_mission(mission_id)
    stored_cards = EvidenceCardRepository(session).list_for_mission(mission_id)
    assert len(stored_sources) == 1
    assert len(stored_cards) == 1
    # Provenance points at a row that exists, with an id persistence assigned.
    assert str(cards[0].source_id) == stored_sources[0].id
    assert cards[0].id is not None


def test_extraction_skips_a_source_already_stored(session: Session) -> None:
    mission_id = create_mission(session)
    stage = evidence_stage(session)
    sources = [source("Grounded retrieval", "https://example.test/a")]

    first = stage.extract(mission_id=mission_id, goal=GOAL, sources=sources)
    second = stage.extract(mission_id=mission_id, goal=GOAL, sources=sources)

    assert len(first) == 1
    assert second == []
    assert len(SourceDocumentRepository(session).list_for_mission(mission_id)) == 1


def test_extraction_scores_relevance_against_the_goal(session: Session) -> None:
    mission_id = create_mission(session)
    sources = [
        source("Retrieval augmented generation quality", "https://example.test/a"),
        SourceResult(
            source_type="arxiv",
            title="Medieval crop rotation",
            url="https://example.test/b",
            content="Manorial ledgers record three-field rotation.",
        ),
    ]

    cards = evidence_stage(session).extract(
        mission_id=mission_id, goal=GOAL, sources=sources
    )

    by_url = {
        str(card.source_id): card.relevance_score for card in cards
    }
    assert len(by_url) == 2
    assert max(by_url.values()) > min(by_url.values())


def test_extraction_of_no_sources_is_a_no_op(session: Session) -> None:
    mission_id = create_mission(session)

    assert evidence_stage(session).extract(
        mission_id=mission_id, goal=GOAL, sources=[]
    ) == []
    assert SourceDocumentRepository(session).list_for_mission(mission_id) == []


def test_evidence_belongs_to_the_mission_that_asked_for_it(
    session: Session,
) -> None:
    mission_id = create_mission(session)
    other_mission = uuid4()

    cards = evidence_stage(session).extract(
        mission_id=mission_id, goal=GOAL, sources=[source("A", "https://example.test/a")]
    )

    assert all(card.mission_id == mission_id for card in cards)
    assert (
        EvidenceCardRepository(session).list_for_mission(other_mission) == []
    )


# ----------------------------------------------------------- whole mission


def test_a_mission_now_runs_from_goal_to_a_poc_candidate(session: Session) -> None:
    """The pipeline the roadmap describes, end to end, entirely offline."""

    mission_id = create_mission(session)

    result = WorkflowService(session, max_iterations=2).run(mission_id)

    assert result.status == "completed"
    assert result.handoff_status == "ready_for_poc", result.error
    assert result.evidence_count > 0
    assert result.poc_candidates
    assert result.decision is not None
    assert result.decision.recommendation == "proceed_with_poc"
    assert MissionService(session).get(mission_id).status == MissionStatus.COMPLETED

    # Every cited evidence id traces to a row stored for this mission.
    stored = {card.id for card in EvidenceCardRepository(session).list_for_mission(mission_id)}
    for candidate in result.poc_candidates:
        assert {str(i) for i in candidate.evidence_ids} <= {str(i) for i in stored}


def test_the_run_records_each_stage_as_an_event(session: Session) -> None:
    mission_id = create_mission(session)

    result = WorkflowService(session, max_iterations=2).run(mission_id)

    types = [event.event_type for event in result.events]
    assert types == [
        "workflow_started",
        "sources_retrieved",
        "evidence_extracted",
        "handoff_produced",
        "decision_made",
        # Phase 11 is not built, so the plan is skipped rather than invented.
        "action_plan_skipped",
        "workflow_completed",
    ]
