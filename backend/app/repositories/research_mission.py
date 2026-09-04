"""Research mission persistence operations."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ResearchMission
from app.schemas.research_mission import (
    ResearchMissionCreate,
    ResearchMissionUpdate,
)


class ResearchMissionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, data: ResearchMissionCreate) -> ResearchMission:
        mission = ResearchMission(title=data.title, goal=data.goal)
        self.session.add(mission)
        self.session.commit()
        self.session.refresh(mission)
        return mission

    def get(self, mission_id: UUID | str) -> ResearchMission | None:
        return self.session.get(ResearchMission, str(mission_id))

    def list(self) -> list[ResearchMission]:
        statement = select(ResearchMission).order_by(
            ResearchMission.created_at.desc(), ResearchMission.id.desc()
        )
        return list(self.session.scalars(statement))

    def update(
        self, mission: ResearchMission, data: ResearchMissionUpdate
    ) -> ResearchMission:
        changes = data.model_dump(exclude_unset=True, exclude_none=True)
        status = changes.get("status")
        if status is not None:
            changes["status"] = status.value
        for field, value in changes.items():
            setattr(mission, field, value)
        self.session.commit()
        self.session.refresh(mission)
        return mission

    def delete(self, mission: ResearchMission) -> None:
        self.session.delete(mission)
        self.session.commit()
