"""Search Agent query-planning and retrieval tests."""

from collections.abc import Sequence
from uuid import UUID

import pytest

from app.agents.search import SearchAgent, SearchPlanningError
from app.core.llm import LLMClient, MockLLMClient
from app.schemas.llm import LLMCompletion, LLMMessage
from app.schemas.search_agent import SearchAgentInput
from app.schemas.source_result import SourceResult

MISSION_ID = UUID("11111111-1111-1111-1111-111111111111")
GOAL = "Evaluate retrieval augmented generation for a customer-support product."


class RecordingRetriever:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def retrieve(self, queries: Sequence[str]) -> Sequence[SourceResult]:
        self.calls.append(list(queries))
        return [
            SourceResult(
                source_type="arxiv",
                title="Retrieved source",
                url="https://example.test/source",
            )
        ]


class StaticLLMClient(LLMClient):
    def __init__(self, response: str) -> None:
        self.response = response

    def complete(self, messages: list[LLMMessage]) -> LLMCompletion:
        del messages
        return LLMCompletion(content=self.response, model="test", mocked=False)


def search_input(**overrides: object) -> SearchAgentInput:
    values: dict[str, object] = {
        "mission_id": MISSION_ID,
        "research_goal": GOAL,
        "iteration": 0,
    }
    values.update(overrides)
    return SearchAgentInput(**values)


def test_mock_first_pass_covers_four_research_dimensions() -> None:
    retriever = RecordingRetriever()

    output = SearchAgent(MockLLMClient(), retriever).run(search_input())

    assert len(output.generated_queries) == 4
    combined = " ".join(output.generated_queries).lower()
    assert "research papers" in combined
    assert "open source" in combined
    assert "benchmarks" in combined
    assert "adoption" in combined
    assert retriever.calls == [output.generated_queries]
    assert len(output.retrieved_sources) == 1


def test_follow_up_targets_gaps_without_repeating_query_history() -> None:
    retriever = RecordingRetriever()
    output = SearchAgent(MockLLMClient(), retriever).run(
        search_input(
            iteration=1,
            missing_evidence=["RAG latency benchmark", "RAG operational risks"],
            query_history=["  rag LATENCY benchmark  "],
        )
    )

    assert output.generated_queries == ["RAG operational risks"]
    assert retriever.calls == [["RAG operational risks"]]


def test_real_plan_is_normalized_deduplicated_and_bounded() -> None:
    retriever = RecordingRetriever()
    client = StaticLLMClient(
        '{"queries":["Query A"," query a ","Query B","Query C",'
        '"Query D","Query E"],"notes":"Candidate plan."}'
    )

    output = SearchAgent(client, retriever).run(search_input())

    assert output.generated_queries == ["Query A", "Query B", "Query C", "Query D"]
    assert retriever.calls == [output.generated_queries]


def test_no_new_query_skips_retrieval() -> None:
    retriever = RecordingRetriever()
    client = StaticLLMClient(
        '{"queries":["Known query"],"notes":"Nothing else was useful."}'
    )

    output = SearchAgent(client, retriever).run(
        search_input(query_history=["known QUERY"])
    )

    assert output.generated_queries == []
    assert output.retrieved_sources == []
    assert retriever.calls == []
    assert "No new query" in output.notes


def test_malformed_query_plan_is_an_explicit_failure() -> None:
    agent = SearchAgent(StaticLLMClient('{"queries":[]}'), RecordingRetriever())

    with pytest.raises(SearchPlanningError, match="search-query contract"):
        agent.run(search_input())
