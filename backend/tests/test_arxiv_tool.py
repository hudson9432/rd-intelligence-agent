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
    results = parse_feed(FIXTURE)

    assert len(results) == 2
    first = results[0]
    assert first.source_type is SourceType.ARXIV
    assert first.title == "Attention Is All You Need"
    assert first.url == "http://arxiv.org/abs/1706.03762v7"
    assert "Ashish Vaswani" in first.authors
    assert first.published_at is not None
    assert first.summary


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
