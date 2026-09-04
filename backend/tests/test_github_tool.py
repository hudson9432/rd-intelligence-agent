"""Tests for the GitHub repository search tool."""

import json
from pathlib import Path

import httpx2 as httpx
import pytest

from app.schemas.source_result import SourceType
from app.tools.github import parse_response, search_github
from app.tools.http import SourceUnavailableError

FIXTURE_TEXT = (
    Path(__file__).resolve().parents[2] / "demo" / "fixtures" / "github_response.json"
).read_text(encoding="utf-8")
FIXTURE_PAYLOAD = json.loads(FIXTURE_TEXT)


def test_parse_response_maps_items_without_fabricating_fields() -> None:
    results = parse_response(FIXTURE_PAYLOAD)

    assert len(results) == 2
    first = results[0]
    assert first.source_type is SourceType.GITHUB
    assert first.title == "huggingface/transformers"
    assert first.url == "https://github.com/huggingface/transformers"
    assert first.authors == ["huggingface"]
    assert first.metadata["language"] == "Python"
    assert first.metadata["updated_at"] == "2026-09-04T05:18:46Z"


def test_parse_response_skips_items_missing_required_fields() -> None:
    incomplete = {"items": [{"description": "no name or url"}]}

    assert parse_response(incomplete) == []


async def test_search_github_uses_query_and_per_page_params() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json=FIXTURE_PAYLOAD)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        results = await search_github(
            "llm agents", 5, client=client, token="github-test-token"
        )

    request = captured["request"]
    assert request.url.params["q"] == "llm agents"
    assert request.url.params["per_page"] == "5"
    assert request.headers["Authorization"] == "Bearer github-test-token"
    assert request.headers["X-GitHub-Api-Version"] == "2022-11-28"

    assert results == parse_response(FIXTURE_PAYLOAD)


async def test_search_github_wraps_malformed_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": None})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SourceUnavailableError, match="malformed response"):
            await search_github("llm agents", 5, client=client)
