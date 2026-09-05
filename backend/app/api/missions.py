"""Research mission HTTP endpoints."""

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from app.api.dependencies import (
    DatabaseSession,
    MissionResultServiceDependency,
    MissionServiceDependency,
    WorkflowServiceDependency,
)
from app.models.agent_event import AgentEvent as AgentEventModel
from app.models.research_mission import ResearchMission as ResearchMissionModel
from app.schemas.agent_event import AgentEvent
from app.schemas.mission_result import MissionResult
from app.schemas.mission_workspace import MissionWorkspace
from app.schemas.research_mission import (
    ResearchMissionCreate,
    ResearchMissionDetail,
    ResearchMissionSummary,
)
from app.schemas.workflow import WorkflowRunAccepted, WorkflowRunResult
from app.services.mission import MissionNotFoundError
from app.services.mission_workspace import MissionWorkspaceService
from app.services.workflow import (
    WorkflowAlreadyRunningError,
    run_workflow_in_background,
)

router = APIRouter(prefix="/missions", tags=["missions"])


def _not_found(error: MissionNotFoundError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": "mission_not_found",
            "message": str(error),
        },
    )


@router.post(
    "",
    response_model=ResearchMissionDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_mission(
    payload: ResearchMissionCreate,
    service: MissionServiceDependency,
) -> ResearchMissionModel:
    return service.create(payload)


@router.get("", response_model=list[ResearchMissionSummary])
def list_missions(service: MissionServiceDependency) -> list[ResearchMissionModel]:
    return service.list()


@router.get("/{mission_id}", response_model=ResearchMissionDetail)
def get_mission(
    mission_id: UUID,
    service: MissionServiceDependency,
) -> ResearchMissionModel:
    try:
        return service.get(mission_id)
    except MissionNotFoundError as error:
        raise _not_found(error) from error


@router.get("/{mission_id}/events", response_model=list[AgentEvent])
def list_mission_events(
    mission_id: UUID,
    service: MissionServiceDependency,
) -> list[AgentEventModel]:
    try:
        return service.list_events(mission_id)
    except MissionNotFoundError as error:
        raise _not_found(error) from error


@router.get("/{mission_id}/result", response_model=MissionResult)
def get_mission_result(
    mission_id: UUID,
    service: MissionResultServiceDependency,
) -> MissionResult:
    """Return the evidence, audit trail, decision, and action plan together."""

    try:
        return service.get(mission_id)
    except MissionNotFoundError as error:
        raise _not_found(error) from error


@router.get("/{mission_id}/workspace", response_model=MissionWorkspace)
def get_mission_workspace(
    mission_id: UUID, session: DatabaseSession
) -> MissionWorkspace:
    try:
        return MissionWorkspaceService(session).get(mission_id)
    except MissionNotFoundError as error:
        raise _not_found(error) from error


@router.post("/{mission_id}/run", response_model=WorkflowRunResult)
def run_mission_workflow(
    mission_id: UUID,
    service: WorkflowServiceDependency,
) -> WorkflowRunResult:
    """Run the mission workflow to a terminal state.

    The run is synchronous: stages are placeholders today, so it returns
    immediately. Moving to a background runner is required before any stage
    performs real network or LLM work.
    """

    try:
        return service.run(mission_id)
    except MissionNotFoundError as error:
        raise _not_found(error) from error
    except WorkflowAlreadyRunningError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "workflow_already_running", "message": str(error)},
        ) from error


@router.post(
    "/{mission_id}/run/async",
    response_model=WorkflowRunAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def run_mission_workflow_in_background(
    mission_id: UUID,
    background_tasks: BackgroundTasks,
    service: WorkflowServiceDependency,
) -> WorkflowRunAccepted:
    """Queue a real-provider workflow without holding the HTTP request open."""

    try:
        claimed_id = service.claim_run(mission_id)
    except MissionNotFoundError as error:
        raise _not_found(error) from error
    except WorkflowAlreadyRunningError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "workflow_already_running", "message": str(error)},
        ) from error

    background_tasks.add_task(run_workflow_in_background, claimed_id)
    return WorkflowRunAccepted(
        mission_id=mission_id,
        mission_url=f"/missions/{mission_id}",
        events_url=f"/missions/{mission_id}/events",
        result_url=f"/missions/{mission_id}/result",
    )
