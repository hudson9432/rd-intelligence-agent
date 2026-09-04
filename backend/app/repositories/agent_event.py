"""Agent event persistence operations."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AgentEvent
from app.schemas.agent_event import AgentEventCreate


class AgentEventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, data: AgentEventCreate) -> AgentEvent:
        event = AgentEvent(
            mission_id=str(data.mission_id),
            agent_name=data.agent_name,
            event_type=data.event_type,
            message=data.message,
            metadata_json=data.metadata,
        )
        self.session.add(event)
        self.session.commit()
        self.session.refresh(event)
        return event

    def list_for_mission(self, mission_id: UUID | str) -> list[AgentEvent]:
        statement = (
            select(AgentEvent)
            .where(AgentEvent.mission_id == str(mission_id))
            .order_by(AgentEvent.created_at, AgentEvent.id)
        )
        return list(self.session.scalars(statement))
