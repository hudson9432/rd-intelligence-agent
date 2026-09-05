"""FastAPI dependency factories."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.mission import MissionService
from app.services.mission_result import MissionResultService
from app.services.workflow import WorkflowService

DatabaseSession = Annotated[Session, Depends(get_db)]


def get_mission_service(session: DatabaseSession) -> MissionService:
    return MissionService(session)


MissionServiceDependency = Annotated[MissionService, Depends(get_mission_service)]


def get_mission_result_service(session: DatabaseSession) -> MissionResultService:
    return MissionResultService(session)


MissionResultServiceDependency = Annotated[
    MissionResultService, Depends(get_mission_result_service)
]


def get_workflow_service(session: DatabaseSession) -> WorkflowService:
    return WorkflowService(session)


WorkflowServiceDependency = Annotated[WorkflowService, Depends(get_workflow_service)]
