"""Mission API contract tests."""

from datetime import datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.repositories import AgentEventRepository
from app.schemas import AgentEventCreate


def test_create_list_get_and_events(client: TestClient, session: Session) -> None:
    create_response = client.post(
        "/missions",
        json={
            "title": "Computer-use agent opportunity",
            "goal": "Find a one-week R&D prototype.",
        },
    )
    assert create_response.status_code == 201
    mission = create_response.json()
    assert mission["status"] == "created"
    assert datetime.fromisoformat(mission["created_at"]) <= datetime.fromisoformat(
        mission["updated_at"]
    )

    list_response = client.get("/missions")
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [mission["id"]]

    detail_response = client.get(f"/missions/{mission['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["goal"] == "Find a one-week R&D prototype."

    AgentEventRepository(session).save(
        AgentEventCreate(
            mission_id=mission["id"],
            agent_name="orchestrator",
            event_type="mission_created",
            message="Mission is ready.",
            metadata={"source": "api-test"},
        )
    )
    events_response = client.get(f"/missions/{mission['id']}/events")
    assert events_response.status_code == 200
    assert events_response.json()[0]["metadata"] == {"source": "api-test"}


def test_missing_mission_returns_consistent_404(client: TestClient) -> None:
    mission_id = uuid4()
    for path in (f"/missions/{mission_id}", f"/missions/{mission_id}/events"):
        response = client.get(path)
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "mission_not_found"
        assert str(mission_id) in response.json()["detail"]["message"]


def test_invalid_mission_id_returns_422(client: TestClient) -> None:
    response = client.get("/missions/not-a-uuid")

    assert response.status_code == 422


def test_create_mission_validates_payload(client: TestClient) -> None:
    response = client.post("/missions", json={"title": "", "goal": ""})

    assert response.status_code == 422
