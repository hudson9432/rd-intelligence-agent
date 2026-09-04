"""Workflow endpoint contract."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import missions as missions_api
from app.schemas.research_mission import MissionStatus, ResearchMissionUpdate
from app.services.mission import MissionService


def create_mission(client: TestClient) -> str:
    response = client.post(
        "/missions",
        json={
            "title": "On-device inference",
            "goal": "Decide whether to invest in quantized on-device models.",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_run_returns_a_result_and_records_events(client: TestClient) -> None:
    mission_id = create_mission(client)

    response = client.post(f"/missions/{mission_id}/run")

    assert response.status_code == 200
    body = response.json()
    assert body["mission_id"] == mission_id
    assert body["status"] == "completed"
    assert body["final_stage"] == "done"
    # No phase is implemented, so the run must report no viable direction.
    assert body["handoff_status"] == "no_viable_direction"
    assert body["poc_candidates"] == []
    assert body["action_plan"] is None

    events = client.get(f"/missions/{mission_id}/events")
    assert events.status_code == 200
    assert [event["event_type"] for event in events.json()] == [
        event["event_type"] for event in body["events"]
    ]

    detail = client.get(f"/missions/{mission_id}")
    assert detail.json()["status"] == "completed"


def test_run_reports_the_bounded_research_loop_in_events(client: TestClient) -> None:
    mission_id = create_mission(client)

    body = client.post(f"/missions/{mission_id}/run").json()

    types = [event["event_type"] for event in body["events"]]
    assert types.count("queries_generated") == body["iterations_used"] + 1
    assert types.count("sources_retrieved") == body["iterations_used"] + 1
    assert body["query_history"]
    assert "research_budget_exhausted" in types


def test_run_on_an_unknown_mission_returns_404(client: TestClient) -> None:
    response = client.post("/missions/00000000-0000-0000-0000-000000000000/run")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "mission_not_found"


def test_run_on_a_running_mission_returns_409(
    client: TestClient, session: Session
) -> None:
    mission_id = create_mission(client)
    MissionService(session).update(
        mission_id, ResearchMissionUpdate(status=MissionStatus.RUNNING)
    )

    response = client.post(f"/missions/{mission_id}/run")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "workflow_already_running"


def test_run_rejects_a_malformed_mission_id(client: TestClient) -> None:
    response = client.post("/missions/not-a-uuid/run")

    assert response.status_code == 422


def test_background_run_returns_202_and_exposes_polling_urls(
    client: TestClient,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mission_id = create_mission(client)
    scheduled: list[str] = []

    def record_scheduled(claimed_id: str) -> None:
        scheduled.append(claimed_id)

    monkeypatch.setattr(
        missions_api,
        "run_workflow_in_background",
        record_scheduled,
    )

    response = client.post(f"/missions/{mission_id}/run/async")

    assert response.status_code == 202
    assert response.json() == {
        "mission_id": mission_id,
        "status": "accepted",
        "message": "Workflow accepted for background execution.",
        "mission_url": f"/missions/{mission_id}",
        "events_url": f"/missions/{mission_id}/events",
    }
    assert scheduled == [mission_id]
    assert MissionService(session).get(mission_id).status == MissionStatus.RUNNING


def test_background_run_rejects_an_already_running_mission(
    client: TestClient,
    session: Session,
) -> None:
    mission_id = create_mission(client)
    MissionService(session).update(
        mission_id, ResearchMissionUpdate(status=MissionStatus.RUNNING)
    )

    response = client.post(f"/missions/{mission_id}/run/async")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "workflow_already_running"
