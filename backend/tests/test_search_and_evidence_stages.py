"""Search and Evidence stages, and the mission they now complete."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.agents.orchestrator import WorkflowStageError
from app.core.config import Settings
from app.core.llm import LLMClient, LLMProviderError, MockLLMClient
from app.repositories.evidence_card import EvidenceCardRepository
from app.repositories.source_document import SourceDocumentRepository
from app.schemas.llm import LLMCompletion, LLMMessage
from app.schemas.research_mission import MissionStatus, ResearchMissionCreate
from app.schemas.search_agent import SearchAgentOutput
from app.schemas.source_result import SourceResult
from app.services.evidence_stage import PersistingEvidenceStage
from app.services.mission import MissionService
from app.services.search_stage import ResearchSourceSearchStage
from app.services.workflow import WorkflowService

GOAL = (
    "Decide whether retrieval augmented generation is reliable enough for our product."
)
SEARCH_MISSION_ID = UUID("11111111-1111-1111-1111-111111111111")


class SequenceLLMClient(LLMClient):
    """Replays scripted responses, repeating the last once they run out.

    A structured call may ask more than once when a response does not match
    its contract, so a double that runs dry would fail on the attempt count
    rather than on the behaviour under test.
    """

    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls = 0

    def complete(self, messages: list[LLMMessage]) -> LLMCompletion:
        del messages
        index = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        return LLMCompletion(
            content=self.responses[index], model="live-stub", mocked=False
        )


class FailingLLMClient(LLMClient):
    def complete(self, messages: list[LLMMessage]) -> LLMCompletion:
        del messages
        raise LLMProviderError("provider unavailable")


def extraction_json(snippet: str) -> str:
    return (
        '{"problem":null,"method":null,"benchmark":null,"result":null,'
        '"limitation":null,"technology_tags":[],'
        f'"evidence_snippets":["{snippet}"],'
        '"relevance_score":0.8,"extraction_confidence":0.9}'
    )


def mock_settings() -> Settings:
    return Settings(mock_external_apis=True, demo_mode=False)


def search_stage() -> ResearchSourceSearchStage:
    return ResearchSourceSearchStage(settings=mock_settings())


def run_search(
    stage: ResearchSourceSearchStage,
    *,
    iteration: int = 0,
    missing_evidence: list[str] | None = None,
    query_history: list[str] | None = None,
) -> SearchAgentOutput:
    return stage.search(
        mission_id=SEARCH_MISSION_ID,
        goal=GOAL,
        missing_evidence=missing_evidence or [],
        query_history=query_history or [],
        iteration=iteration,
    )


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


def test_search_plans_first_pass_queries_and_returns_sources() -> None:
    output = run_search(search_stage())

    assert len(output.generated_queries) == 4
    assert output.retrieved_sources
    assert {result.source_type for result in output.retrieved_sources} == {
        "arxiv",
        "github",
    }


def test_search_does_not_return_a_source_twice_across_rounds() -> None:
    """A re-search round must add evidence, not re-extract what is held."""

    stage = search_stage()

    first = run_search(stage)
    second = run_search(
        stage,
        iteration=1,
        missing_evidence=["RAG failure benchmarks"],
        query_history=first.generated_queries,
    )

    assert first.retrieved_sources
    assert second.generated_queries == ["RAG failure benchmarks"]
    # Mock replay ignores the query, so round two is entirely a repeat. That
    # is the documented offline limitation, and the stage must absorb it.
    assert second.retrieved_sources == []


def test_each_stage_instance_starts_with_no_memory() -> None:
    """Seen-source memory must not leak between missions."""

    first = run_search(search_stage())
    second = run_search(search_stage())

    assert first == second


def test_search_planning_provider_failure_is_not_an_empty_search() -> None:
    stage = ResearchSourceSearchStage(
        settings=mock_settings(),
        llm_client=FailingLLMClient(),
    )

    with pytest.raises(
        WorkflowStageError, match="search-query provider request failed"
    ):
        run_search(stage)


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

    by_url = {str(card.source_id): card.relevance_score for card in cards}
    assert len(by_url) == 2
    assert max(by_url.values()) > min(by_url.values())


def test_extraction_of_no_sources_is_a_no_op(session: Session) -> None:
    mission_id = create_mission(session)

    assert (
        evidence_stage(session).extract(mission_id=mission_id, goal=GOAL, sources=[])
        == []
    )
    assert SourceDocumentRepository(session).list_for_mission(mission_id) == []


def test_all_invalid_provider_outputs_fail_instead_of_looking_like_no_evidence(
    session: Session,
) -> None:
    mission_id = create_mission(session)
    stage = PersistingEvidenceStage(
        session,
        llm_client=SequenceLLMClient(["not-json", "also-not-json"]),
    )

    with pytest.raises(WorkflowStageError, match="all 2 new source"):
        stage.extract(
            mission_id=mission_id,
            goal=GOAL,
            sources=[
                source("First", "https://example.test/a"),
                source("Second", "https://example.test/b"),
            ],
        )


def test_a_source_without_evidence_is_retried_instead_of_silently_skipped(
    session: Session,
) -> None:
    mission_id = create_mission(session)
    candidate = source("First", "https://example.test/a")

    with pytest.raises(WorkflowStageError):
        PersistingEvidenceStage(
            session,
            llm_client=SequenceLLMClient(["not-json"]),
        ).extract(mission_id=mission_id, goal=GOAL, sources=[candidate])

    cards = PersistingEvidenceStage(
        session,
        llm_client=SequenceLLMClient(
            [extraction_json("The method improves grounded answer quality.")]
        ),
    ).extract(mission_id=mission_id, goal=GOAL, sources=[candidate])

    assert len(cards) == 1
    assert len(SourceDocumentRepository(session).list_for_mission(mission_id)) == 1


def test_one_invalid_provider_output_does_not_discard_valid_evidence(
    session: Session,
) -> None:
    mission_id = create_mission(session)
    valid_snippet = "The method improves grounded answer quality."
    stage = PersistingEvidenceStage(
        session,
        # A structured call asks twice before giving up, so the first source
        # only fails if both of its attempts come back malformed. The third
        # response, repeated by the double, serves the second source.
        llm_client=SequenceLLMClient(
            ["not-json", "not-json", extraction_json(valid_snippet)]
        ),
    )

    cards = stage.extract(
        mission_id=mission_id,
        goal=GOAL,
        sources=[
            source("First", "https://example.test/a"),
            source("Second", "https://example.test/b"),
        ],
    )

    assert len(cards) == 1
    assert cards[0].evidence_snippets_json == [valid_snippet]


def test_provider_transport_failure_becomes_a_workflow_stage_error(
    session: Session,
) -> None:
    mission_id = create_mission(session)
    stage = PersistingEvidenceStage(session, llm_client=FailingLLMClient())

    with pytest.raises(WorkflowStageError, match="provider request failed"):
        stage.extract(
            mission_id=mission_id,
            goal=GOAL,
            sources=[source("First", "https://example.test/a")],
        )


def test_evidence_belongs_to_the_mission_that_asked_for_it(
    session: Session,
) -> None:
    mission_id = create_mission(session)
    other_mission = uuid4()

    cards = evidence_stage(session).extract(
        mission_id=mission_id,
        goal=GOAL,
        sources=[source("A", "https://example.test/a")],
    )

    assert all(card.mission_id == mission_id for card in cards)
    assert EvidenceCardRepository(session).list_for_mission(other_mission) == []


# ----------------------------------------------------------- whole mission


def test_a_mission_now_runs_from_goal_to_a_poc_candidate(session: Session) -> None:
    """The pipeline the roadmap describes, end to end, entirely offline."""

    mission_id = create_mission(session)

    result = WorkflowService(session, max_iterations=2).run(mission_id)

    assert result.status == "completed"
    assert result.handoff_status == "ready_for_poc", result.error
    assert result.evidence_count > 0
    assert len(result.query_history) == 4
    assert len({query.casefold() for query in result.query_history}) == 4
    assert result.poc_candidates
    assert result.decision is not None
    assert result.decision.recommendation == "proceed_with_poc"
    assert MissionService(session).get(mission_id).status == MissionStatus.COMPLETED

    # Every cited evidence id traces to a row stored for this mission.
    stored = {
        card.id for card in EvidenceCardRepository(session).list_for_mission(mission_id)
    }
    for candidate in result.poc_candidates:
        assert {str(i) for i in candidate.evidence_ids} <= {str(i) for i in stored}


def test_the_run_records_each_stage_as_an_event(session: Session) -> None:
    mission_id = create_mission(session)

    result = WorkflowService(session, max_iterations=2).run(mission_id)

    types = [event.event_type for event in result.events]
    assert types == [
        "workflow_started",
        "queries_generated",
        "sources_retrieved",
        "evidence_extracted",
        "handoff_produced",
        "decision_made",
        "action_plan_created",
        "workflow_completed",
    ]
    completed = result.events[-1]
    assert completed.metadata["evidence_count"] == result.evidence_count
    assert completed.metadata["decision"] == result.decision.model_dump(mode="json")
    assert completed.metadata["poc_candidates"]
