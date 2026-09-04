"""Research-source search wired as a workflow stage.

Phase 05. Runs the mission's current queries through `ResearchSourceService`
and hands the orchestrator normalized, deduplicated sources.

Query *authorship* is not here. Round one searches the mission goal; later
rounds search whatever the Critic asked for, which arrives through
`TargetedResearchRequest`. Deciding what to ask is Phase C's job under
`docs/PHASE_C_CONTRACT.md`, so this stage only executes and merges.

A source already seen in an earlier round is dropped, so a re-search round adds
evidence rather than re-extracting what the mission already holds.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

from app.core.config import Settings
from app.schemas.source_result import SourceResult, SourceType
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
        settings: Settings | None = None,
        sources: Sequence[SourceType] | None = None,
        max_results_per_source: int = DEFAULT_MAX_RESULTS_PER_SOURCE,
    ) -> None:
        self._service = service or ResearchSourceService(settings)
        self._sources = tuple(sources) if sources else None
        self._max_results_per_source = max_results_per_source
        self._seen: set[tuple[str, str]] = set()

    def search(
        self, *, goal: str, queries: Sequence[str], iteration: int
    ) -> Sequence[SourceResult]:
        del goal, iteration  # The queries already carry both.

        fresh: list[SourceResult] = []
        for query in queries:
            response = run_blocking(self._run_query(query))
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
