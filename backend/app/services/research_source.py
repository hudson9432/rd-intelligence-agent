"""Research source search service.

Fans out to arXiv and GitHub, tolerates a single source failing, and
deduplicates the combined results. Mock mode replays fixed fixtures through
the exact same parsers the real HTTP path uses, so real and mock output are
structurally identical.
"""

import asyncio
import json
from pathlib import Path

import httpx

from app.core.config import Settings, get_settings
from app.schemas.source_result import SourceError, SourceResult, SourceSearchResponse, SourceType
from app.tools.arxiv import parse_feed, search_arxiv
from app.tools.dedupe import dedupe_results
from app.tools.github import parse_response, search_github
from app.tools.http import SourceUnavailableError

FIXTURES_DIR = Path(__file__).resolve().parents[3] / "demo" / "fixtures"


class ResearchSourceService:
    """Coordinates external source tools behind a single search operation."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def search(self, query: str, max_results: int) -> SourceSearchResponse:
        if self._settings.mock_external_apis or self._settings.demo_mode:
            arxiv_results, arxiv_error = self._load_arxiv_fixture(), None
            github_results, github_error = self._load_github_fixture(), None
        else:
            async with httpx.AsyncClient() as client:
                (arxiv_results, arxiv_error), (github_results, github_error) = await asyncio.gather(
                    self._call_arxiv(client, query, max_results),
                    self._call_github(client, query, max_results),
                )

        merged = dedupe_results(arxiv_results + github_results)
        errors = [error for error in (arxiv_error, github_error) if error is not None]

        return SourceSearchResponse(query=query, results=merged, errors=errors)

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
            return await search_github(query, max_results, client=client), None
        except SourceUnavailableError as exc:
            return [], SourceError(source_type=SourceType.GITHUB, message=str(exc))

    def _load_arxiv_fixture(self) -> list[SourceResult]:
        feed_xml = (FIXTURES_DIR / "arxiv_response.xml").read_text(encoding="utf-8")
        return parse_feed(feed_xml)

    def _load_github_fixture(self) -> list[SourceResult]:
        payload = json.loads((FIXTURES_DIR / "github_response.json").read_text(encoding="utf-8"))
        return parse_response(payload)
