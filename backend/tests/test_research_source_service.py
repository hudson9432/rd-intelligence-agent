"""Tests for the research source search service.

Covers the two hard requirements for this phase: mock and real code paths
must produce structurally identical output, and one source failing must not
prevent the other from returning results.
"""

from app.core.config import Settings
from app.schemas.source_result import SourceResult, SourceType
from app.services import research_source as research_source_module
from app.services.research_source import ResearchSourceService
from app.tools.http import SourceUnavailableError


def _mock_settings() -> Settings:
    return Settings(mock_external_apis=True, demo_mode=False)


def _real_settings() -> Settings:
    return Settings(mock_external_apis=False, demo_mode=False)


async def test_mock_mode_returns_deduplicated_fixture_results() -> None:
    service = ResearchSourceService(settings=_mock_settings())

    response = await service.search("transformers", 10)

    assert response.errors == []
    assert len(response.results) == 4
    source_types = {result.source_type for result in response.results}
    assert source_types == {SourceType.ARXIV, SourceType.GITHUB}


async def test_real_mode_output_matches_mock_mode_shape(monkeypatch) -> None:
    mock_service = ResearchSourceService(settings=_mock_settings())
    mock_response = await mock_service.search("transformers", 10)

    async def fake_search_arxiv(query: str, max_results: int, *, client) -> list[SourceResult]:
        return mock_service._load_arxiv_fixture()

    async def fake_search_github(query: str, max_results: int, *, client) -> list[SourceResult]:
        return mock_service._load_github_fixture()

    monkeypatch.setattr(research_source_module, "search_arxiv", fake_search_arxiv)
    monkeypatch.setattr(research_source_module, "search_github", fake_search_github)

    real_service = ResearchSourceService(settings=_real_settings())
    real_response = await real_service.search("transformers", 10)

    exclude = {"id", "retrieved_at"}
    mock_dump = [r.model_dump(exclude=exclude) for r in mock_response.results]
    real_dump = [r.model_dump(exclude=exclude) for r in real_response.results]
    assert mock_dump == real_dump
    assert real_response.errors == []


async def test_one_source_failing_still_returns_the_other(monkeypatch) -> None:
    mock_service = ResearchSourceService(settings=_mock_settings())
    github_fixture = mock_service._load_github_fixture()

    async def failing_arxiv(query: str, max_results: int, *, client) -> list[SourceResult]:
        raise SourceUnavailableError("arxiv unreachable")

    async def working_github(query: str, max_results: int, *, client) -> list[SourceResult]:
        return github_fixture

    monkeypatch.setattr(research_source_module, "search_arxiv", failing_arxiv)
    monkeypatch.setattr(research_source_module, "search_github", working_github)

    service = ResearchSourceService(settings=_real_settings())
    response = await service.search("transformers", 10)

    assert len(response.errors) == 1
    assert response.errors[0].source_type is SourceType.ARXIV
    assert len(response.results) == len(github_fixture)
    assert all(r.source_type is SourceType.GITHUB for r in response.results)


async def test_both_sources_failing_returns_no_results_and_two_errors(monkeypatch) -> None:
    async def failing_arxiv(query: str, max_results: int, *, client) -> list[SourceResult]:
        raise SourceUnavailableError("arxiv unreachable")

    async def failing_github(query: str, max_results: int, *, client) -> list[SourceResult]:
        raise SourceUnavailableError("github unreachable")

    monkeypatch.setattr(research_source_module, "search_arxiv", failing_arxiv)
    monkeypatch.setattr(research_source_module, "search_github", failing_github)

    service = ResearchSourceService(settings=_real_settings())
    response = await service.search("transformers", 10)

    assert response.results == []
    assert len(response.errors) == 2
