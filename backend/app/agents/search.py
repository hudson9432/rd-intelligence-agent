"""History-aware Search Agent with deterministic retrieval boundaries."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.core.llm import LLMClient, LLMStructuredOutputError
from app.prompts.search import build_search_messages
from app.schemas.search_agent import SearchAgentInput, SearchAgentOutput
from app.schemas.source_result import SourceResult

MAX_GENERATED_QUERY_CANDIDATES = 12
DEFAULT_MAX_QUERIES = 4
QueryCandidate = Annotated[str, Field(min_length=1, max_length=500)]


class _QueryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    queries: list[QueryCandidate] = Field(
        min_length=1, max_length=MAX_GENERATED_QUERY_CANDIDATES
    )
    notes: str = Field(min_length=1)


class SearchRetriever(Protocol):
    """Deterministic source-tool boundary used by the Search Agent."""

    def retrieve(self, queries: Sequence[str]) -> Sequence[SourceResult]: ...


class SearchPlanningError(RuntimeError):
    """Raised when a provider cannot produce a valid search plan."""


class SearchAgent:
    """Plan bounded queries, remove history duplicates, and retrieve sources."""

    def __init__(
        self,
        llm_client: LLMClient,
        retriever: SearchRetriever,
        *,
        max_queries: int = DEFAULT_MAX_QUERIES,
    ) -> None:
        if not 1 <= max_queries <= DEFAULT_MAX_QUERIES:
            raise ValueError("max_queries must be between 1 and 4")
        self._llm_client = llm_client
        self._retriever = retriever
        self._max_queries = max_queries

    def run(self, data: SearchAgentInput) -> SearchAgentOutput:
        """Generate new queries before invoking deterministic source tools."""

        try:
            plan = self._llm_client.complete_structured(
                build_search_messages(data),
                _QueryPlan,
                mock_factory=lambda: _mock_query_plan(data),
            )
        except LLMStructuredOutputError as error:
            raise SearchPlanningError(
                "LLM response did not match the search-query contract"
            ) from error

        queries = _select_new_queries(
            plan.queries,
            query_history=data.query_history,
            limit=self._max_queries,
        )
        sources = list(self._retriever.retrieve(queries)) if queries else []
        notes = plan.notes
        if not queries:
            notes = f"{notes} No new query remained after history deduplication."
        return SearchAgentOutput(
            generated_queries=queries,
            retrieved_sources=sources,
            notes=notes,
        )


def _mock_query_plan(data: SearchAgentInput) -> _QueryPlan:
    if data.iteration == 0:
        goal = data.research_goal
        queries = [
            f"{goal} recent research papers",
            f"{goal} open source implementations",
            f"{goal} benchmarks performance evaluation",
            f"{goal} technical adoption feasibility",
        ]
        notes = (
            "Deterministic first-pass plan covers research, implementations, "
            "benchmarks, and adoption."
        )
    else:
        queries = data.missing_evidence or [
            f"{data.research_goal} unresolved evidence gaps"
        ]
        notes = "Deterministic follow-up plan targets the supplied evidence gaps."

    return _QueryPlan(
        queries=[_bounded_query(query) for query in queries],
        notes=notes,
    )


def _select_new_queries(
    candidates: Sequence[str], *, query_history: Sequence[str], limit: int
) -> list[str]:
    seen = {_query_key(query) for query in query_history}
    selected: list[str] = []
    for candidate in candidates:
        normalized = _bounded_query(candidate)
        key = _query_key(normalized)
        if not key or key in seen:
            continue
        seen.add(key)
        selected.append(normalized)
        if len(selected) >= limit:
            break
    return selected


def _bounded_query(value: str) -> str:
    return " ".join(value.split())[:500].strip()


def _query_key(value: str) -> str:
    return " ".join(value.casefold().split())
