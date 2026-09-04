"""Tests for concurrent, deterministic research-source orchestration."""

from datetime import UTC, datetime

from app.core.config import Settings
from app.schemas.source_result import SourceResult, SourceType
from app.services import research_source as research_source_module
from app.services.research_source import ResearchSourceService
from app.tools.http import SourceUnavailableError


def _mock_settings() -> Settings:
    return Settings(mock_external_apis=True, demo_mode=False)


def _real_settings(**overrides: object) -> Settings:
    return Settings(
        mock_external_apis=False,
        demo_mode=False,
        **overrides,
    )


async def test_mock_mode_is_deterministic_and_deduplicated() -> None:
    service = ResearchSourceService(settings=_mock_settings())

    first = await service.search("transformers", max_results_per_source=10)
    second = await service.search("transformers", max_results_per_source=10)

    assert first == second
    assert first.errors == []
    assert len(first.results) == 4
    assert {result.source_type for result in first.results} == {
        SourceType.ARXIV,
        SourceType.GITHUB,
    }


async def test_mock_mode_honors_source_selection_and_per_source_limit() -> None:
    service = ResearchSourceService(settings=_mock_settings())

    response = await service.search(
        "transformers",
        sources=[SourceType.GITHUB],
        max_results_per_source=1,
    )

    assert len(response.results) == 1
    assert response.results[0].source_type is SourceType.GITHUB


async def test_mock_mode_filters_by_published_date() -> None:
    service = ResearchSourceService(settings=_mock_settings())

    response = await service.search(
        "transformers",
        max_results_per_source=10,
        published_after=datetime(2021, 1, 1, tzinfo=UTC),
    )

    assert response.results
    assert all(
        result.published_at is not None
        and result.published_at >= datetime(2021, 1, 1, tzinfo=UTC)
        for result in response.results
    )


async def test_real_mode_output_matches_mock_mode(
    monkeypatch,
) -> None:
    mock_service = ResearchSourceService(settings=_mock_settings())
    mock_response = await mock_service.search("transformers", max_results_per_source=10)

    async def fake_search_arxiv(
        query: str, max_results: int, *, client
    ) -> list[SourceResult]:
        return mock_service._load_arxiv_fixture()

    async def fake_search_github(
        query: str,
        max_results: int,
        *,
        client,
        token: str | None = None,
    ) -> list[SourceResult]:
        return mock_service._load_github_fixture()

    monkeypatch.setattr(research_source_module, "search_arxiv", fake_search_arxiv)
    monkeypatch.setattr(research_source_module, "search_github", fake_search_github)

    real_service = ResearchSourceService(settings=_real_settings())
    real_response = await real_service.search("transformers", max_results_per_source=10)

    assert real_response == mock_response


async def test_service_passes_optional_github_token(monkeypatch) -> None:
    captured: dict[str, str | None] = {}

    async def fake_search_github(
        query: str,
        max_results: int,
        *,
        client,
        token: str | None = None,
    ) -> list[SourceResult]:
        captured["token"] = token
        return []

    monkeypatch.setattr(research_source_module, "search_github", fake_search_github)

    service = ResearchSourceService(
        settings=_real_settings(github_token="github-test-token")
    )
    await service.search(
        "transformers",
        sources=[SourceType.GITHUB],
        max_results_per_source=1,
    )

    assert captured["token"] == "github-test-token"


async def test_one_source_failing_still_returns_the_other(monkeypatch) -> None:
    mock_service = ResearchSourceService(settings=_mock_settings())
    github_fixture = mock_service._load_github_fixture()

    async def failing_arxiv(
        query: str, max_results: int, *, client
    ) -> list[SourceResult]:
        raise SourceUnavailableError("arxiv unreachable")

    async def working_github(
        query: str,
        max_results: int,
        *,
        client,
        token: str | None = None,
    ) -> list[SourceResult]:
        return github_fixture

    monkeypatch.setattr(research_source_module, "search_arxiv", failing_arxiv)
    monkeypatch.setattr(research_source_module, "search_github", working_github)

    service = ResearchSourceService(settings=_real_settings())
    response = await service.search("transformers", max_results_per_source=10)

    assert len(response.errors) == 1
    assert response.errors[0].source_type is SourceType.ARXIV
    assert len(response.results) == len(github_fixture)
    assert all(result.source_type is SourceType.GITHUB for result in response.results)


async def test_both_sources_failing_returns_no_results_and_two_errors(
    monkeypatch,
) -> None:
    async def failing_arxiv(
        query: str, max_results: int, *, client
    ) -> list[SourceResult]:
        raise SourceUnavailableError("arxiv unreachable")

    async def failing_github(
        query: str,
        max_results: int,
        *,
        client,
        token: str | None = None,
    ) -> list[SourceResult]:
        raise SourceUnavailableError("github unreachable")

    monkeypatch.setattr(research_source_module, "search_arxiv", failing_arxiv)
    monkeypatch.setattr(research_source_module, "search_github", failing_github)

    service = ResearchSourceService(settings=_real_settings())
    response = await service.search("transformers", max_results_per_source=10)

    assert response.results == []
    assert len(response.errors) == 2
