"""Search Agent query planning and deterministic source retrieval.

Phase 05. The agent turns a goal or Critic-supplied evidence gaps into bounded,
history-aware queries. This stage then executes those queries through
`ResearchSourceService` and removes sources already seen during the run.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar
from uuid import UUID

from app.agents.orchestrator import WorkflowStageError
from app.agents.search import SearchAgent, SearchPlanningError
from app.core.config import Settings, get_settings
from app.core.llm import LLMClient, LLMProviderError, get_llm_client
from app.schemas.search_agent import SearchAgentInput, SearchAgentOutput
from app.schemas.source_result import SourceError, SourceResult, SourceType
from app.services.research_source import ResearchSourceService
from app.tools.dedupe import content_hash, normalize_url

T = TypeVar("T")

DEFAULT_MAX_RESULTS_PER_SOURCE = 8


def run_blocking(coroutine: Coroutine[Any, Any, T]) -> T:
    """Run a coroutine from synchronous code.

    The workflow graph is synchronous while the source tools are async. The
    endpoint that drives a run is a sync `def`, so FastAPI calls it on a
    worker thread with no running loop and `asyncio.run` applies. An async
    caller — a test, or a future async endpoint — would already hold a loop, so
    the coroutine goes to a thread of its own instead of raising.
    """

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)

    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coroutine).result()


def _identity(result: SourceResult) -> tuple[str, str]:
    """The pair `dedupe_results` uses, so both agree on what is a duplicate."""

    return (
        normalize_url(result.url),
        content_hash(result.title, result.summary or "", result.content or ""),
    )


class ResearchSourceSearchStage:
    """Executes the mission's queries against the configured sources."""

    def __init__(
        self,
        service: ResearchSourceService | None = None,
        *,
        llm_client: LLMClient | None = None,
        settings: Settings | None = None,
        sources: Sequence[SourceType] | None = None,
        max_results_per_source: int = DEFAULT_MAX_RESULTS_PER_SOURCE,
    ) -> None:
        resolved_settings = settings or get_settings()
        self._service = service or ResearchSourceService(resolved_settings)
        self._sources = tuple(sources) if sources else None
        self._max_results_per_source = max_results_per_source
        self._seen: set[tuple[str, str]] = set()
        self._round_errors: list[SourceError] = []
        self._agent = SearchAgent(
            llm_client or get_llm_client(resolved_settings),
            self,
        )

    def search(
        self,
        *,
        mission_id: UUID,
        goal: str,
        missing_evidence: Sequence[str],
        query_history: Sequence[str],
        iteration: int,
    ) -> SearchAgentOutput:
        self._round_errors = []
        try:
            output = self._agent.run(
                SearchAgentInput(
                    mission_id=mission_id,
                    research_goal=goal,
                    missing_evidence=list(missing_evidence),
                    query_history=list(query_history),
                    iteration=iteration,
                )
            )
            # The agent plans and retrieves; the failures surface here because
            # only this stage talks to the source service.
            return output.model_copy(update={"source_errors": list(self._round_errors)})
        except LLMProviderError as error:
            raise WorkflowStageError(
                "The search-query provider request failed; no query was executed."
            ) from error
        except SearchPlanningError as error:
            raise WorkflowStageError(
                f"The search-query provider returned an unusable response: {error}"
            ) from error

    def retrieve(self, queries: Sequence[str]) -> Sequence[SourceResult]:
        """Execute planned queries and return only sources new to this run."""

        fresh: list[SourceResult] = []
        for query in queries:
            response = run_blocking(self._run_query(query))
            self._round_errors.extend(response.errors)
            for result in response.results:
                identity = _identity(result)
                if identity in self._seen:
                    continue
                self._seen.add(identity)
                fresh.append(result)
        return fresh

    async def _run_query(self, query: str) -> Any:
        kwargs: dict[str, Any] = {
            "max_results_per_source": self._max_results_per_source
        }
        if self._sources is not None:
            kwargs["sources"] = list(self._sources)
        return await self._service.search(query, **kwargs)
