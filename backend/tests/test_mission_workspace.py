"""The dashboard read model exposes real persisted results and provenance."""

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.schemas.research_mission import MissionStatus, ResearchMissionUpdate
from app.services.mission import MissionService
from app.services.workflow import WorkflowService


def create(client: TestClient) -> str:
    return client.post("/missions", json={
        "title": "RAG evaluation",
        "goal": "Decide whether retrieval augmented generation is reliable enough for our product.",
    }).json()["id"]


def test_empty_workspace_and_missing_mission(client: TestClient) -> None:
    mission_id = create(client)
    response = client.get(f"/missions/{mission_id}/workspace")
    assert response.status_code == 200
    data = response.json()
    assert data["mission"]["id"] == mission_id
    for key in ("sources", "evidence", "opportunities", "events"):
        assert data[key] == []
    assert data["summary"] is None
    assert data["action_plan"] is None
    assert client.get(f"/missions/{uuid4()}/workspace").status_code == 404
    assert client.get("/missions/invalid/workspace").status_code == 422


def test_offline_workflow_results_are_readable_and_mission_scoped(
    client: TestClient, session: Session,
) -> None:
    mission_id = create(client)
    result = WorkflowService(session).run(mission_id)
    assert result.status == "completed", result.error
    assert result.action_plan is not None
    response = client.get(f"/missions/{mission_id}/workspace")
    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["decision"] == result.decision.model_dump(mode="json")
    assert data["action_plan"]["tasks_json"]
    assert data["opportunities"]
    source_ids = {source["id"] for source in data["sources"]}
    evidence_ids = {card["id"] for card in data["evidence"]}
    for card in data["evidence"]:
        assert card["source_id"] in source_ids
        assert card["mission_id"] == mission_id
    for opportunity in data["opportunities"]:
        assert set(opportunity["related_evidence_ids_json"]) <= evidence_ids
    other = client.get(f"/missions/{create(client)}/workspace").json()
    assert other["evidence"] == []
    assert other["action_plan"] is None

    # A claimed retry must not display the previous completed run as current.
    WorkflowService(session).claim_run(mission_id)
    running = client.get(f"/missions/{mission_id}/workspace").json()
    assert running["summary"] is None
    assert running["action_plan"] is None
    assert running["opportunities"] == []
    assert running["evidence"]  # Saved provenance is not erased by a retry.
    MissionService(session).update(mission_id, ResearchMissionUpdate(status=MissionStatus.FAILED))
    failed = client.get(f"/missions/{mission_id}/workspace").json()
    assert failed["summary"] is None
    assert failed["action_plan"] is None
