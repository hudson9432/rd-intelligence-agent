"""Research source search service.

Fans out to arXiv and GitHub, tolerates a single source failing, and
deduplicates the combined results. Mock mode replays fixed fixtures through
the exact same parsers the real HTTP path uses, so real and mock output are
structurally identical.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path

import httpx2 as httpx

from app.core.config import Settings, get_settings
from app.schemas.source_result import (
    SourceError,
    SourceResult,
    SourceSearchResponse,
    SourceType,
)
from app.tools.arxiv import parse_feed, search_arxiv
from app.tools.dedupe import dedupe_results
from app.tools.github import parse_response, search_github
from app.tools.http import SourceUnavailableError

FIXTURES_DIR = Path(__file__).resolve().parents[3] / "demo" / "fixtures"
DEFAULT_SOURCES = (SourceType.ARXIV, SourceType.GITHUB)


class ResearchSourceService:
    """Coordinates external source tools behind a single search operation."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def search(
        self,
        query: str,
        *,
        sources: list[SourceType] | tuple[SourceType, ...] = DEFAULT_SOURCES,
        max_results_per_source: int = 5,
        published_after: datetime | None = None,
    ) -> SourceSearchResponse:
        source_results: list[SourceResult] = []
        errors: list[SourceError] = []

        if self._settings.mock_external_apis or self._settings.demo_mode:
            for source_type in sources:
                fixture_results = self._load_fixture(source_type)
                source_results.extend(fixture_results[:max_results_per_source])
        else:
            async with httpx.AsyncClient() as client:
                outcomes = await asyncio.gather(
                    *(
                        self._call_source(
                            source_type,
                            client,
                            query,
                            max_results_per_source,
                        )
                        for source_type in sources
                    )
                )
            for results, error in outcomes:
                source_results.extend(results)
                if error is not None:
                    errors.append(error)

        if published_after is not None:
            source_results = [
                result
                for result in source_results
                if result.published_at is not None
                and result.published_at >= published_after
            ]

        return SourceSearchResponse(
            query=query,
            results=dedupe_results(source_results),
            errors=errors,
        )

    async def _call_source(
        self,
        source_type: SourceType,
        client: httpx.AsyncClient,
        query: str,
        max_results: int,
    ) -> tuple[list[SourceResult], SourceError | None]:
        if source_type is SourceType.ARXIV:
            return await self._call_arxiv(client, query, max_results)
        return await self._call_github(client, query, max_results)

    async def _call_arxiv(
        self, client: httpx.AsyncClient, query: str, max_results: int
    ) -> tuple[list[SourceResult], SourceError | None]:
        try:
            return await search_arxiv(query, max_results, client=client), None
        except SourceUnavailableError as exc:
            return [], SourceError(source_type=SourceType.ARXIV, message=str(exc))

    async def _call_github(
        self, client: httpx.AsyncClient, query: str, max_results: int
    ) -> tuple[list[SourceResult], SourceError | None]:
        try:
            token = (
                self._settings.github_token.get_secret_value()
                if self._settings.github_token is not None
                else None
            )
            return await search_github(
                query,
                max_results,
                client=client,
                token=token,
            ), None
        except SourceUnavailableError as exc:
            return [], SourceError(source_type=SourceType.GITHUB, message=str(exc))

    def _load_arxiv_fixture(self) -> list[SourceResult]:
        feed_xml = (FIXTURES_DIR / "arxiv_response.xml").read_text(encoding="utf-8")
        return parse_feed(feed_xml)

    def _load_github_fixture(self) -> list[SourceResult]:
        payload = json.loads(
            (FIXTURES_DIR / "github_response.json").read_text(encoding="utf-8")
        )
        return parse_response(payload)

    def _load_fixture(self, source_type: SourceType) -> list[SourceResult]:
        if source_type is SourceType.ARXIV:
            return self._load_arxiv_fixture()
        return self._load_github_fixture()
