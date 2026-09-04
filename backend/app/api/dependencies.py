"""FastAPI dependency factories."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.mission import MissionService

DatabaseSession = Annotated[Session, Depends(get_db)]


def get_mission_service(session: DatabaseSession) -> MissionService:
    return MissionService(session)


MissionServiceDependency = Annotated[MissionService, Depends(get_mission_service)]
