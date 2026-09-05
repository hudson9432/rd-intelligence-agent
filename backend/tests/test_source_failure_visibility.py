"""A source that cannot be reached must say so, not look like an empty result.

A live run spent two re-search rounds and roughly twenty provider calls while
arXiv was throttling every request. The stage read `SourceSearchResponse.results`
and dropped `.errors`, so the workflow reported `sources_retrieved +0` and
nothing anywhere said arXiv had failed. The run read as "targeted re-search
found no new evidence" when it was "the source was unreachable" — a difference
that changes what a reader should conclude and what an operator should do.
"""

from collections.abc import Sequence
from uuid import UUID, uuid4

from app.agents.orchestrator import WorkflowOrchestrator, WorkflowStages
from app.agents.pending_stages import PendingActionStage, PendingDecisionStage
from app.core.config import Settings
from app.core.llm import MockLLMClient
from app.schemas.search_agent import SearchAgentOutput
from app.schemas.source_result import (
    SourceError,
    SourceResult,
    SourceSearchResponse,
    SourceType,
)
from app.schemas.workflow import WorkflowState
from app.services.analysis_stage import PhaseCAnalysisStage
from app.services.search_stage import ResearchSourceSearchStage
from tests.test_workflow_orchestrator import MISSION_ID, make_source

GOAL = "Decide whether the approach is worth a proof of concept."


class FailingSourceService:
    """Stands in for a provider that is throttling or down."""

    def __init__(
        self,
        *,
        results: Sequence[SourceResult] = (),
        errors: Sequence[SourceError] = (),
    ) -> None:
        self.results = list(results)
        self.errors = list(errors)
        self.queries: list[str] = []

    async def search(self, query: str, **kwargs: object) -> SourceSearchResponse:
        del kwargs
        self.queries.append(query)
        return SourceSearchResponse(
            query=query, results=self.results, errors=self.errors
        )


def arxiv_is_down() -> SourceError:
    return SourceError(
        source_type=SourceType.ARXIV,
        message="https://export.arxiv.org/api/query failed after 3 attempts",
    )


def stage(service: FailingSourceService) -> ResearchSourceSearchStage:
    return ResearchSourceSearchStage(
        service,
        settings=Settings(mock_external_apis=True, demo_mode=False),
        llm_client=MockLLMClient(),
    )


def run_search(service: FailingSourceService) -> SearchAgentOutput:
    return stage(service).search(
        mission_id=MISSION_ID,
        goal=GOAL,
        missing_evidence=[],
        query_history=[],
        iteration=0,
    )


def test_a_failed_source_is_reported_not_swallowed() -> None:
    service = FailingSourceService(errors=[arxiv_is_down()])

    output = run_search(service)

    assert output.retrieved_sources == []
    assert output.source_errors, "the failure must not be dropped"
    assert output.source_errors[0].source_type is SourceType.ARXIV


def test_a_partial_failure_keeps_the_sources_that_did_arrive() -> None:
    """One provider being down must not discard the other's results."""

    service = FailingSourceService(results=[make_source("a")], errors=[arxiv_is_down()])

    output = run_search(service)

    assert len(output.retrieved_sources) == 1
    # One failure per planned query, so the count reflects attempts, not sources.
    assert output.source_errors
    assert {error.source_type for error in output.source_errors} == {SourceType.ARXIV}


def test_a_clean_empty_result_reports_no_failure() -> None:
    """Finding nothing and failing to look are different outcomes."""

    output = run_search(FailingSourceService())

    assert output.retrieved_sources == []
    assert output.source_errors == []


def test_errors_do_not_leak_between_rounds() -> None:
    service = FailingSourceService(errors=[arxiv_is_down()])
    search_stage = stage(service)

    first = search_stage.search(
        mission_id=MISSION_ID,
        goal=GOAL,
        missing_evidence=[],
        query_history=[],
        iteration=0,
    )
    service.errors = []
    second = search_stage.search(
        mission_id=MISSION_ID,
        goal=GOAL,
        missing_evidence=["a follow-up gap"],
        query_history=list(first.generated_queries),
        iteration=1,
    )

    assert first.source_errors
    assert second.source_errors == [], "a recovered round must look recovered"


class ScriptedSearch:
    """Search stage returning a fixed output, to drive the graph directly."""

    def __init__(self, output: SearchAgentOutput) -> None:
        self.output = output

    def search(self, **kwargs: object) -> SearchAgentOutput:
        del kwargs
        return self.output


class NoEvidence:
    def extract(self, *, mission_id: UUID, goal: str, sources: Sequence[SourceResult]):
        del mission_id, goal, sources
        return []


def test_the_workflow_emits_an_event_a_reader_can_see() -> None:
    """The whole point: the failure reaches the mission event stream."""

    output = SearchAgentOutput(
        generated_queries=["a query"],
        retrieved_sources=[],
        source_errors=[arxiv_is_down()],
        notes="planned",
    )
    stages = WorkflowStages(
        search=ScriptedSearch(output),
        evidence=NoEvidence(),
        analysis=PhaseCAnalysisStage(MockLLMClient()),
        decision=PendingDecisionStage(),
        action=PendingActionStage(),
    )

    result = WorkflowOrchestrator(stages).run(
        WorkflowState(mission_id=uuid4(), goal=GOAL, max_iterations=1)
    )

    unavailable = [
        event for event in result.events if event.event_type == "source_unavailable"
    ]
    assert unavailable, "a reader of the event stream must learn arXiv was down"
    event = unavailable[0]
    assert "arxiv" in event.message
    assert event.metadata["failures"][0]["source_type"] == "arxiv"
    assert event.metadata["failures"][0]["queries"] >= 1
    # It must not be mistaken for the run failing outright.
    assert result.status == "completed"


def test_no_event_is_emitted_when_every_source_answered() -> None:
    output = SearchAgentOutput(
        generated_queries=["a query"],
        retrieved_sources=[make_source("a")],
        notes="planned",
    )
    stages = WorkflowStages(
        search=ScriptedSearch(output),
        evidence=NoEvidence(),
        analysis=PhaseCAnalysisStage(MockLLMClient()),
        decision=PendingDecisionStage(),
        action=PendingActionStage(),
    )

    result = WorkflowOrchestrator(stages).run(
        WorkflowState(mission_id=uuid4(), goal=GOAL, max_iterations=1)
    )

    assert not [
        event for event in result.events if event.event_type == "source_unavailable"
    ]
