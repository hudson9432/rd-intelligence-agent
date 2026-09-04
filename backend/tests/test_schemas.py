"""Validation tests for public persistence contracts."""

from uuid import uuid4

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings
from app.schemas import (
    EvidenceCardCreate,
    ResearchMissionCreate,
    TechnologyOpportunityCreate,
)


def test_research_mission_create_validates_required_text() -> None:
    payload = ResearchMissionCreate(
        title="Computer-use agents", goal="Find a one-week PoC"
    )

    assert payload.title == "Computer-use agents"
    with pytest.raises(ValidationError):
        ResearchMissionCreate(title="", goal="")


def test_evidence_scores_are_bounded() -> None:
    with pytest.raises(ValidationError):
        EvidenceCardCreate(
            mission_id=uuid4(),
            source_id=uuid4(),
            relevance_score=1.1,
            extraction_confidence=0.8,
        )


def test_opportunity_scores_are_bounded() -> None:
    with pytest.raises(ValidationError):
        TechnologyOpportunityCreate(
            mission_id=uuid4(),
            name="Recovery loop",
            description="Detect and repair failed GUI actions.",
            novelty=6,
            technical_maturity=3,
            implementation_difficulty=3,
            business_impact=5,
            poc_feasibility=4,
            evidence_strength=3,
            overall_score=75,
            rationale="Useful for reliable automation.",
        )


def test_api_key_is_stored_as_secret() -> None:
    settings = Settings(llm_api_key="not-a-real-secret")

    assert isinstance(settings.llm_api_key, SecretStr)
    assert "not-a-real-secret" not in repr(settings)
