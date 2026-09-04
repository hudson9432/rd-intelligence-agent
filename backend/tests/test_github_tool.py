"""Tests for the GitHub repository search tool."""

import json
from pathlib import Path

import httpx

from app.schemas.source_result import SourceType
from app.tools.github import parse_response, search_github

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
    assert first.normalized_url
    assert first.content_hash


def test_parse_response_skips_items_missing_required_fields() -> None:
    incomplete = {"items": [{"description": "no name or url"}]}

    assert parse_response(incomplete) == []


async def test_search_github_uses_query_and_per_page_params() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json=FIXTURE_PAYLOAD)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        results = await search_github("llm agents", 5, client=client)

    request = captured["request"]
    assert request.url.params["q"] == "llm agents"
    assert request.url.params["per_page"] == "5"

    exclude = {"id", "retrieved_at"}
    actual = [r.model_dump(exclude=exclude) for r in results]
    expected = [r.model_dump(exclude=exclude) for r in parse_response(FIXTURE_PAYLOAD)]
    assert actual == expected
