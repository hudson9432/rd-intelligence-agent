"""Tests for the arXiv search tool."""

from pathlib import Path

import httpx2 as httpx
import pytest

from app.schemas.source_result import SourceType
from app.tools.arxiv import parse_feed, search_arxiv
from app.tools.http import SourceUnavailableError

FIXTURE = (
    Path(__file__).resolve().parents[2] / "demo" / "fixtures" / "arxiv_response.xml"
).read_text(encoding="utf-8")


def test_parse_feed_maps_entries_without_fabricating_fields() -> None:
    """Assert on structure, not on which papers were captured.

    The fixture is refreshed by `demo/capture_fixtures.py`, so pinning titles
    here would make every refresh a test failure. Checking that each mapped
    value occurs verbatim in the feed is also a stronger anti-fabrication
    assertion than comparing against a remembered string.
    """

    results = parse_feed(FIXTURE)

    assert results, "the committed fixture must contain parseable entries"
    for result in results:
        assert result.source_type is SourceType.ARXIV
        assert result.title
        assert result.title in " ".join(FIXTURE.split())
        assert result.url.startswith("http")
        assert result.url in FIXTURE
        for author in result.authors:
            assert author in FIXTURE

    assert any(result.authors for result in results)
    assert any(result.published_at is not None for result in results)
    assert any(result.summary for result in results)


def test_parse_feed_skips_entries_missing_required_fields() -> None:
    incomplete_feed = """<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <summary>No id or title here.</summary>
      </entry>
    </feed>"""

    assert parse_feed(incomplete_feed) == []


async def test_search_arxiv_uses_query_and_max_results_params() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, text=FIXTURE)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        results = await search_arxiv("transformers", 5, client=client)

    request = captured["request"]
    assert request.url.params["search_query"] == "all:transformers"
    assert request.url.params["max_results"] == "5"

    assert results == parse_feed(FIXTURE)


async def test_search_arxiv_wraps_malformed_xml() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not xml")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SourceUnavailableError, match="malformed XML"):
            await search_arxiv("transformers", 5, client=client)
