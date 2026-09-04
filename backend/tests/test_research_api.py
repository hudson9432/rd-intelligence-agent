"""Contract tests for the research search endpoint."""

from fastapi.testclient import TestClient


def test_search_endpoint_honors_sources_and_per_source_limit(
    client: TestClient,
) -> None:
    response = client.post(
        "/research/search",
        json={
            "query": "transformers",
            "sources": ["arxiv", "github"],
            "max_results_per_source": 1,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "transformers"
    assert body["errors"] == []
    assert len(body["results"]) == 2
    assert {result["source_type"] for result in body["results"]} == {
        "arxiv",
        "github",
    }
    assert all("id" not in result for result in body["results"])
    assert all("retrieved_at" not in result for result in body["results"])


def test_search_endpoint_can_select_one_source(client: TestClient) -> None:
    response = client.post(
        "/research/search",
        json={
            "query": "transformers",
            "sources": ["github"],
            "max_results_per_source": 1,
        },
    )

    assert response.status_code == 200
    assert [result["source_type"] for result in response.json()["results"]] == [
        "github"
    ]


def test_search_endpoint_rejects_invalid_request(client: TestClient) -> None:
    invalid_payloads = [
        {"query": "   "},
        {"query": "test", "sources": []},
        {"query": "test", "sources": ["github", "github"]},
        {"query": "test", "sources": ["web"]},
        {"query": "test", "max_results_per_source": 0},
        {"query": "test", "max_results": 5},
    ]

    for payload in invalid_payloads:
        assert client.post("/research/search", json=payload).status_code == 422


def test_openapi_contains_search_route(client: TestClient) -> None:
    schema = client.app.openapi()

    assert "/research/search" in schema["paths"]
