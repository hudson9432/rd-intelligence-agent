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
ADVERSARIAL_QUERY_SUFFIX = "failure limitations negative results contradictory evidence"
QueryCandidate = Annotated[str, Field(min_length=1, max_length=500)]


class _QueryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    queries: list[QueryCandidate] = Field(
        min_length=1, max_length=MAX_GENERATED_QUERY_CANDIDATES
    )
    repository_queries: list[QueryCandidate] = Field(
        default_factory=list, max_length=MAX_GENERATED_QUERY_CANDIDATES
    )
    """Short keyword queries for code hosting search.

    Optional on purpose. A planner that omits it leaves retrieval exactly as it
    was rather than introducing a new way for a round to fail.
    """

    notes: str = ""
    """Free-text explanation, required of nobody.

    A provider given a second list to fill has been observed dropping this one
    instead. It carries no decision, so failing a whole retrieval round over its
    absence would cost far more than it is worth.
    """


class SearchRetriever(Protocol):
    """Deterministic source-tool boundary used by the Search Agent."""

    def retrieve(
        self, queries: Sequence[str], repository_queries: Sequence[str] = ()
    ) -> Sequence[SourceResult]: ...


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

        queries = _select_query_portfolio(
            plan.queries,
            data=data,
            limit=self._max_queries,
        )
        repository_queries = _select_new_queries(
            plan.repository_queries,
            query_history=data.query_history,
            limit=self._max_queries,
        )
        sources = (
            list(self._retriever.retrieve(queries, repository_queries))
            if queries
            else []
        )
        notes = plan.notes.strip() or "The planner returned no explanation."
        if not queries:
            notes = f"{notes} No new query remained after history deduplication."
        return SearchAgentOutput(
            generated_queries=queries,
            repository_queries=repository_queries,
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
            _adversarial_query(goal),
        ]
        notes = (
            "Deterministic first-pass plan covers research, implementations, "
            "benchmarks, and disconfirming evidence."
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


def _select_query_portfolio(
    candidates: Sequence[str], *, data: SearchAgentInput, limit: int
) -> list[str]:
    """Reserve one first-pass slot for disconfirming evidence.

    A live planner can omit an adversarial query even when the prompt requests
    one. The portfolio rule therefore lives in deterministic code. Follow-up
    rounds remain entirely driven by Critic evidence gaps.
    """

    if data.iteration != 0:
        return _select_new_queries(
            candidates, query_history=data.query_history, limit=limit
        )

    adversarial = _adversarial_query(data.research_goal)
    history_keys = {_query_key(query) for query in data.query_history}
    adversarial_is_new = _query_key(adversarial) not in history_keys
    ordinary_limit = limit - int(adversarial_is_new)
    ordinary = _select_new_queries(
        candidates,
        query_history=[*data.query_history, adversarial],
        limit=ordinary_limit,
    )
    if adversarial_is_new:
        ordinary.append(adversarial)
    return ordinary


def _select_new_queries(
    candidates: Sequence[str], *, query_history: Sequence[str], limit: int
) -> list[str]:
    if limit <= 0:
        return []
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


def _adversarial_query(goal: str) -> str:
    return _bounded_query(f"{goal} {ADVERSARIAL_QUERY_SUFFIX}")
