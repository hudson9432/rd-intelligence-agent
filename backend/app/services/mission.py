"""Research mission application service."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.agent_event import AgentEvent
from app.models.research_mission import ResearchMission
from app.repositories.agent_event import AgentEventRepository
from app.repositories.research_mission import ResearchMissionRepository
from app.schemas.research_mission import ResearchMissionCreate, ResearchMissionUpdate


class MissionNotFoundError(LookupError):
    def __init__(self, mission_id: UUID | str) -> None:
        self.mission_id = str(mission_id)
        super().__init__(f"Research mission {self.mission_id} was not found")


class MissionService:
    def __init__(self, session: Session) -> None:
        self.missions = ResearchMissionRepository(session)
        self.events = AgentEventRepository(session)

    def create(self, data: ResearchMissionCreate) -> ResearchMission:
        return self.missions.create(data)

    def get(self, mission_id: UUID | str) -> ResearchMission:
        mission = self.missions.get(mission_id)
        if mission is None:
            raise MissionNotFoundError(mission_id)
        return mission

    def list(self) -> list[ResearchMission]:
        return self.missions.list()

    def update(
        self, mission_id: UUID | str, data: ResearchMissionUpdate
    ) -> ResearchMission:
        return self.missions.update(self.get(mission_id), data)

    def list_events(self, mission_id: UUID | str) -> list[AgentEvent]:
        self.get(mission_id)
        return self.events.list_for_mission(mission_id)
