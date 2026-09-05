"""Validation tests for public persistence and workflow contracts."""

from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings
from app.schemas import (
    EvidenceCardCreate,
    ResearchMissionCreate,
    SourceResult,
    SourceSearchRequest,
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
            goal_alignment=5,
            poc_feasibility=4,
            evidence_strength=3,
            overall_score=75,
            rationale="Useful for reliable automation.",
        )


def test_api_key_is_stored_as_secret() -> None:
    settings = Settings(
        llm_api_key="not-a-real-secret",
        github_token="not-a-real-github-token",
    )

    assert isinstance(settings.llm_api_key, SecretStr)
    assert isinstance(settings.github_token, SecretStr)
    assert "not-a-real-secret" not in repr(settings)
    assert "not-a-real-github-token" not in repr(settings)


def test_source_result_uses_provider_neutral_fields_and_utc_time() -> None:
    published_at = datetime(2026, 9, 4, 12, tzinfo=timezone(timedelta(hours=8)))

    source = SourceResult(
        source_type="arxiv",
        title="Reliable agents",
        url="https://arxiv.org/abs/9999.99999",
        published_at=published_at,
        authors=["Ada Researcher"],
        summary="A source summary.",
        metadata={"category": "cs.AI"},
    )

    assert source.published_at == datetime(2026, 9, 4, 4, tzinfo=UTC)
    assert source.authors == ["Ada Researcher"]
    assert source.summary == "A source summary."
    assert source.metadata == {"category": "cs.AI"}


def test_source_result_rejects_naive_published_time() -> None:
    naive_time = datetime(2026, 9, 4, tzinfo=UTC).replace(tzinfo=None)

    with pytest.raises(ValidationError, match="timezone"):
        SourceResult(
            source_type="github",
            title="Agent repository",
            url="https://github.com/example/agent",
            published_at=naive_time,
        )


def test_source_search_request_normalizes_query_and_date() -> None:
    request = SourceSearchRequest(
        query="  computer-use agents  ",
        sources=["github"],
        max_results_per_source=3,
        published_after="2026-09-04T12:00:00+08:00",
    )

    assert request.query == "computer-use agents"
    assert request.sources == ["github"]
    assert request.published_after == datetime(2026, 9, 4, 4, tzinfo=UTC)
