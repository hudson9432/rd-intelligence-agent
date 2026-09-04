"""Research mission HTTP endpoints."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import (
    MissionServiceDependency,
    WorkflowServiceDependency,
)
from app.models.agent_event import AgentEvent as AgentEventModel
from app.models.research_mission import ResearchMission as ResearchMissionModel
from app.schemas.agent_event import AgentEvent
from app.schemas.research_mission import (
    ResearchMissionCreate,
    ResearchMissionDetail,
    ResearchMissionSummary,
)
from app.schemas.workflow import WorkflowRunResult
from app.services.mission import MissionNotFoundError
from app.services.workflow import WorkflowAlreadyRunningError

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
