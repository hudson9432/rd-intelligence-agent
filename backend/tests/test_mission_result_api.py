"""Mission result API and an offline e-commerce audit scenario."""

from fastapi.testclient import TestClient

ECOMMERCE_GOAL = (
    "Decide whether retrieval augmented generation is reliable enough "
    "for an e-commerce product."
)


def create_ecommerce_mission(client: TestClient) -> str:
    response = client.post(
        "/missions",
        json={
            "title": "E-commerce RAG reliability",
            "goal": ECOMMERCE_GOAL,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_result_before_a_run_is_an_empty_read_model(client: TestClient) -> None:
    mission_id = create_ecommerce_mission(client)

    response = client.get(f"/missions/{mission_id}/result")

    assert response.status_code == 200
    result = response.json()
    assert result["mission"]["id"] == mission_id
    assert result["mission"]["status"] == "created"
    assert result["sources"] == []
    assert result["evidence"] == []
    assert result["handoff"] is None
    assert result["audit"] is None
    assert result["opportunities"] == []
    assert result["decision"] is None
    assert result["action_plan"] is None


def test_ecommerce_mission_returns_an_auditable_result(client: TestClient) -> None:
    """Frozen real RAG sources exercise a contextual e-commerce decision."""

    mission_id = create_ecommerce_mission(client)
    run_response = client.post(f"/missions/{mission_id}/run")
    assert run_response.status_code == 200
    assert run_response.json()["status"] == "completed"

    response = client.get(f"/missions/{mission_id}/result")

    assert response.status_code == 200
    result = response.json()
    assert result["mission"]["goal"] == ECOMMERCE_GOAL
    assert result["mission"]["status"] == "completed"
    assert result["sources"]
    assert result["evidence"]
    assert result["handoff"]["status"] == "ready_for_poc"
    assert result["decision"]["recommendation"] == "proceed_with_poc"
    assert result["opportunities"]
    assert result["action_plan"]["tasks_json"]

    audit = result["audit"]
    assert audit["status"] == "needs_review"
    sufficiency = audit["evidence_sufficiency"]
    assert sufficiency["sufficient"] is True
    assert sufficiency["effective_evidence_count"] >= 2
    assert sufficiency["independent_source_count"] >= 2
    assert len(sufficiency["assessments"]) == len(result["evidence"])

    evidence_ids = {item["id"] for item in result["evidence"]}
    source_ids = {item["id"] for item in result["sources"]}
    assert {item["source_id"] for item in result["evidence"]} <= source_ids
    assert set(audit["accepted_evidence_ids"]) <= evidence_ids
    assert {item["evidence_id"] for item in audit["excluded_evidence"]} <= evidence_ids
    assert set(audit["supporting_evidence_ids"]) <= evidence_ids
    assert set(audit["opposing_evidence_ids"]) <= evidence_ids

    verdict_counts = audit["claim_verdict_counts"]
    assert sum(verdict_counts.values()) == len(result["handoff"]["claim_assessments"])
    assert {item["code"] for item in audit["findings"]} == {
        "all_claims_unknown",
        "most_evidence_excluded",
        "no_counterevidence",
        "no_result_bearing_evidence",
    }
    assert set(audit["supporting_evidence_ids"]) <= set(audit["accepted_evidence_ids"])
    assert (
        audit["highest_opportunity_score"]
        == result["opportunities"][0]["overall_score"]
    )
    scores = [item["overall_score"] for item in result["opportunities"]]
    assert scores == sorted(scores, reverse=True)


def test_result_for_an_unknown_mission_returns_404(client: TestClient) -> None:
    response = client.get("/missions/00000000-0000-0000-0000-000000000000/result")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "mission_not_found"


def test_result_explains_an_insufficient_research_outcome(
    client: TestClient,
) -> None:
    created = client.post(
        "/missions",
        json={
            "title": "Unrelated domain",
            "goal": "Assess medieval crop rotation records.",
        },
    )
    mission_id = created.json()["id"]

    run_response = client.post(f"/missions/{mission_id}/run")
    result = client.get(f"/missions/{mission_id}/result").json()

    assert run_response.status_code == 200
    assert result["handoff"]["status"] == "no_viable_direction"
    assert result["audit"]["status"] == "insufficient"
    assert result["audit"]["evidence_sufficiency"]["sufficient"] is False
    assert "insufficient_evidence_pool" in {
        finding["code"] for finding in result["audit"]["findings"]
    }
    assert result["opportunities"] == []
    assert result["decision"]["recommendation"] == "do_not_proceed"
    assert result["action_plan"] is None
