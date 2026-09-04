"""Workflow persistence: events, mission status, and action plans."""

import pytest
from sqlalchemy.orm import Session

from app.db.session import create_database_engine, create_session_factory, init_db
from app.repositories.action_plan import ActionPlanRepository
from app.repositories.agent_event import AgentEventRepository
from app.schemas.research_mission import MissionStatus, ResearchMissionCreate
from app.services.mission import MissionNotFoundError, MissionService
from app.services.workflow import (
    WorkflowAlreadyRunningError,
    WorkflowService,
    run_workflow_in_background,
)
from tests.test_workflow_orchestrator import (
    PlanningAction,
    RecordingSearch,
    ScriptedAnalysis,
    ScriptedEvidence,
    build_stages,
    make_evidence,
    make_poc_handoff,
    make_source,
)


def create_mission(session: Session) -> str:
    mission = MissionService(session).create(
        ResearchMissionCreate(
            title="On-device inference",
            goal="Decide whether to invest in quantized on-device models.",
        )
    )
    return mission.id


def test_run_persists_every_event_and_completes_the_mission(session: Session) -> None:
    mission_id = create_mission(session)
    service = WorkflowService(session, max_iterations=2)

    result = service.run(mission_id)

    assert result.status == "completed"
    stored = AgentEventRepository(session).list_for_mission(mission_id)
    assert [event.event_type for event in stored] == [
        event.event_type for event in result.events
    ]
    assert MissionService(session).get(mission_id).status == MissionStatus.COMPLETED


def test_events_carry_structured_metadata(session: Session) -> None:
    """The default stage set now really searches, so counts are non-zero."""

    mission_id = create_mission(session)

    WorkflowService(session, max_iterations=1).run(mission_id)

    stored = AgentEventRepository(session).list_for_mission(mission_id)
    started = next(e for e in stored if e.event_type == "workflow_started")
    assert started.metadata_json == {"max_iterations": 1}
    retrieved = next(e for e in stored if e.event_type == "sources_retrieved")
    assert retrieved.metadata_json["iteration"] == 0
    assert retrieved.metadata_json["source_count"] > 0
    assert retrieved.metadata_json["queries"]
    extracted = next(e for e in stored if e.event_type == "evidence_extracted")
    assert extracted.metadata_json["total_count"] > 0


def test_run_stores_a_produced_action_plan(session: Session) -> None:
    mission_id = create_mission(session)
    stages = build_stages(
        search=RecordingSearch([[make_source("a")]]),
        evidence=ScriptedEvidence([[make_evidence()]]),
        analysis=ScriptedAnalysis([make_poc_handoff()]),
        action=PlanningAction(),
    )

    result = WorkflowService(session, stages=stages).run(mission_id)

    assert result.action_plan is not None
    stored = ActionPlanRepository(session).get_for_mission(mission_id)
    assert stored is not None
    assert stored.title == "PoC for d1"
    assert len(stored.tasks_json) == 1


def test_a_failed_run_marks_the_mission_failed(session: Session) -> None:
    from tests.test_workflow_orchestrator import FailingSearch

    mission_id = create_mission(session)
    service = WorkflowService(session, stages=build_stages(search=FailingSearch()))

    result = service.run(mission_id)

    assert result.status == "failed"
    assert MissionService(session).get(mission_id).status == MissionStatus.FAILED
    stored = AgentEventRepository(session).list_for_mission(mission_id)
    assert stored[-1].event_type == "workflow_failed"


def test_an_unexpected_sync_failure_does_not_strand_the_mission_running(
    session: Session,
) -> None:
    class UnexpectedFailure:
        def search(self, **kwargs: object) -> list[object]:
            del kwargs
            raise RuntimeError("unexpected bug")

    mission_id = create_mission(session)
    service = WorkflowService(
        session,
        stages=build_stages(search=UnexpectedFailure()),
    )

    with pytest.raises(RuntimeError, match="unexpected bug"):
        service.run(mission_id)

    assert MissionService(session).get(mission_id).status == MissionStatus.FAILED


def test_running_an_in_progress_mission_is_rejected(session: Session) -> None:
    mission_id = create_mission(session)
    missions = MissionService(session)
    from app.schemas.research_mission import ResearchMissionUpdate

    missions.update(mission_id, ResearchMissionUpdate(status=MissionStatus.RUNNING))

    with pytest.raises(WorkflowAlreadyRunningError):
        WorkflowService(session).run(mission_id)


def test_running_an_unknown_mission_raises(session: Session) -> None:
    with pytest.raises(MissionNotFoundError):
        WorkflowService(session).run("00000000-0000-0000-0000-000000000000")


def test_a_completed_mission_can_be_run_again(session: Session) -> None:
    mission_id = create_mission(session)
    service = WorkflowService(session, max_iterations=1)

    first = service.run(mission_id)
    second = service.run(mission_id)

    assert first.status == "completed"
    assert second.status == "completed"
    stored = AgentEventRepository(session).list_for_mission(mission_id)
    assert len(stored) == len(first.events) + len(second.events)


def test_a_claimed_mission_can_run_in_a_separate_execution_step(
    session: Session,
) -> None:
    mission_id = create_mission(session)
    service = WorkflowService(session, max_iterations=1)

    claimed_id = service.claim_run(mission_id)

    assert claimed_id == mission_id
    assert MissionService(session).get(mission_id).status == MissionStatus.RUNNING

    result = service.run_claimed(claimed_id)

    assert result.status == "completed"
    assert MissionService(session).get(mission_id).status == MissionStatus.COMPLETED


def test_background_runner_uses_an_independent_database_session(tmp_path) -> None:
    database_engine = create_database_engine(f"sqlite:///{tmp_path / 'background.db'}")
    init_db(database_engine)
    factory = create_session_factory(database_engine)

    with factory() as setup_session:
        mission_id = create_mission(setup_session)
        WorkflowService(setup_session).claim_run(mission_id)

    run_workflow_in_background(mission_id, session_factory=factory)

    with factory() as verification_session:
        mission = MissionService(verification_session).get(mission_id)
        events = AgentEventRepository(verification_session).list_for_mission(mission_id)

    database_engine.dispose()
    assert mission.status == MissionStatus.COMPLETED
    assert events[-1].event_type == "workflow_completed"
