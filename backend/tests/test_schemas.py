"""Smoke tests for the initial typed schemas."""

from uuid import uuid4

from pydantic import SecretStr

from app.core.config import Settings
from app.schemas import AgentEvent, MissionStatus, ResearchMission


def test_research_mission_defaults() -> None:
    mission = ResearchMission(title="Computer-use agents", goal="Find a one-week PoC")

    assert mission.status is MissionStatus.CREATED
    assert mission.created_at.tzinfo is not None
    assert mission.updated_at.tzinfo is not None


def test_agent_event_defaults() -> None:
    event = AgentEvent(
        mission_id=uuid4(),
        agent_name="orchestrator",
        event_type="mission_created",
        message="Mission is ready.",
    )

    assert event.metadata == {}
    assert event.created_at.tzinfo is not None


def test_api_key_is_stored_as_secret() -> None:
    settings = Settings(llm_api_key="not-a-real-secret")

    assert isinstance(settings.llm_api_key, SecretStr)
    assert "not-a-real-secret" not in repr(settings)
