"""Tests for POST /research/search."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_search_endpoint_returns_deduplicated_results_in_mock_mode() -> None:
    response = client.post("/research/search", json={"query": "transformers", "max_results": 10})

    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "transformers"
    assert body["errors"] == []
    assert len(body["results"]) == 4
    assert {r["source_type"] for r in body["results"]} == {"arxiv", "github"}


def test_search_endpoint_rejects_empty_query() -> None:
    response = client.post("/research/search", json={"query": ""})

    assert response.status_code == 422


def test_openapi_contains_search_route() -> None:
    schema = app.openapi()

    assert "/research/search" in schema["paths"]
