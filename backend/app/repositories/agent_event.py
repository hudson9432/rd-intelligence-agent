"""Agent event persistence operations."""

from datetime import timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AgentEvent
from app.models.mixins import utc_now
from app.schemas.agent_event import AgentEventCreate


class AgentEventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, data: AgentEventCreate) -> AgentEvent:
        created_at = utc_now()
        latest_created_at = self.session.scalar(
            select(AgentEvent.created_at)
            .where(AgentEvent.mission_id == str(data.mission_id))
            .order_by(AgentEvent.created_at.desc())
            .limit(1)
        )
        if latest_created_at is not None and created_at <= latest_created_at:
            # SQLite can persist several fast events with the same clock tick.
            # Give the later event a stable ordering key rather than falling
            # back to its random UUID.
            created_at = latest_created_at + timedelta(microseconds=1)

        event = AgentEvent(
            mission_id=str(data.mission_id),
            agent_name=data.agent_name,
            event_type=data.event_type,
            message=data.message,
            metadata_json=data.metadata,
            created_at=created_at,
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
