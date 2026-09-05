"""Repository persistence, provenance, ordering, and cascade tests."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    ActionPlan,
    AgentEvent,
    CoverageReport,
    EvidenceCard,
    ResearchMission,
    SourceDocument,
    TechnologyOpportunity,
)
from app.repositories import (
    ActionPlanRepository,
    AgentEventRepository,
    CoverageReportRepository,
    EvidenceCardRepository,
    ResearchMissionRepository,
    SourceDocumentRepository,
    TechnologyOpportunityRepository,
)
from app.schemas import (
    ActionPlanCreate,
    ActionTask,
    AgentEventCreate,
    CoverageReportCreate,
    EvidenceCardCreate,
    MissionStatus,
    ResearchMissionCreate,
    ResearchMissionUpdate,
    SourceDocumentCreate,
    TechnologyOpportunityCreate,
)


def create_mission(
    session: Session, title: str = "Computer-use agents"
) -> ResearchMission:
    return ResearchMissionRepository(session).create(
        ResearchMissionCreate(title=title, goal="Find a one-week PoC")
    )


def create_source(session: Session, mission: ResearchMission) -> SourceDocument:
    return SourceDocumentRepository(session).save(
        SourceDocumentCreate(
            mission_id=mission.id,
            source_type="arxiv",
            title="Reliable Computer-Use Agents",
            url=f"https://example.test/{mission.id}/paper",
            published_at=datetime(2026, 1, 2, tzinfo=UTC),
            authors_json=["Ada Researcher"],
            raw_summary="Recovery improves reliability.",
            content="Measured recovery results and limitations.",
            content_hash="a" * 64,
        )
    )


def create_evidence(
    session: Session,
    mission: ResearchMission,
    source: SourceDocument,
) -> EvidenceCard:
    return EvidenceCardRepository(session).save(
        EvidenceCardCreate(
            mission_id=mission.id,
            source_id=source.id,
            problem="GUI agents fail after unexpected state changes.",
            method="Failure detection followed by replanning.",
            benchmark="Offline GUI task suite",
            result="Higher recovery success rate.",
            limitation="Small evaluation set.",
            technology_tags_json=["computer-use", "recovery"],
            evidence_snippets_json=["Recovery improved successful completion."],
            relevance_score=0.95,
            extraction_confidence=0.9,
        )
    )


def test_mission_create_list_get_and_update(session: Session) -> None:
    repository = ResearchMissionRepository(session)
    first = repository.create(
        ResearchMissionCreate(title="First", goal="First research goal")
    )
    second = repository.create(
        ResearchMissionCreate(title="Second", goal="Second research goal")
    )

    assert repository.get(first.id) is first
    assert [mission.id for mission in repository.list()] == [second.id, first.id]

    updated = repository.update(
        first,
        ResearchMissionUpdate(status=MissionStatus.RUNNING, title="Updated"),
    )
    assert updated.title == "Updated"
    assert updated.status == "running"
    assert updated.created_at <= updated.updated_at
    assert updated.updated_at.tzinfo is UTC


def test_source_and_evidence_json_round_trip(session: Session) -> None:
    mission = create_mission(session)
    source = create_source(session, mission)
    evidence = create_evidence(session, mission, source)

    stored_source = SourceDocumentRepository(session).list_for_mission(mission.id)[0]
    stored_evidence = EvidenceCardRepository(session).list_for_mission(mission.id)[0]
    assert stored_source.authors_json == ["Ada Researcher"]
    assert stored_evidence.technology_tags_json == ["computer-use", "recovery"]
    assert source.published_at is not None
    assert source.published_at.tzinfo is UTC
    assert evidence.source_id == source.id


def test_evidence_rejects_cross_mission_source(session: Session) -> None:
    first = create_mission(session, "First")
    second = create_mission(session, "Second")
    source = create_source(session, first)

    with pytest.raises(ValueError, match="same mission"):
        EvidenceCardRepository(session).save(
            EvidenceCardCreate(
                mission_id=second.id,
                source_id=source.id,
                relevance_score=0.8,
                extraction_confidence=0.8,
            )
        )


def test_opportunities_are_ranked_and_preserve_evidence_ids(session: Session) -> None:
    mission = create_mission(session)
    source = create_source(session, mission)
    evidence = create_evidence(session, mission, source)
    repository = TechnologyOpportunityRepository(session)

    for name, score in (("Lower", 60), ("Self-Healing Agent", 88)):
        repository.save(
            TechnologyOpportunityCreate(
                mission_id=mission.id,
                name=name,
                description="Detect failures and recover.",
                related_evidence_ids_json=[evidence.id],
                novelty=4,
                technical_maturity=3,
                implementation_difficulty=3,
                goal_alignment=5,
                poc_feasibility=4,
                evidence_strength=4,
                overall_score=score,
                rationale="Evidence supports a focused PoC.",
            )
        )

    opportunities = repository.list_for_mission(mission.id)
    assert [item.name for item in opportunities] == ["Self-Healing Agent", "Lower"]
    assert opportunities[0].related_evidence_ids_json == [evidence.id]


def test_latest_coverage_and_same_iteration_update(session: Session) -> None:
    mission = create_mission(session)
    repository = CoverageReportRepository(session)

    first = repository.save(
        CoverageReportCreate(
            mission_id=mission.id,
            overall_score=50,
            sufficient=False,
            dimension_status_json={"novelty": "adequate", "benchmark": "absent"},
            missing_evidence_json=["benchmark"],
            suggested_queries_json=["computer agent recovery benchmark"],
            iteration=1,
        )
    )
    changed = repository.save(
        CoverageReportCreate(
            mission_id=mission.id,
            overall_score=58,
            sufficient=False,
            dimension_status_json={"novelty": "adequate", "benchmark": "weak"},
            iteration=1,
        )
    )
    second = repository.save(
        CoverageReportCreate(
            mission_id=mission.id,
            overall_score=83,
            sufficient=True,
            dimension_status_json={"novelty": "adequate", "benchmark": "adequate"},
            iteration=2,
        )
    )

    assert changed.id == first.id
    assert repository.get_latest(mission.id) is second


def test_action_plan_is_replaced_per_mission(session: Session) -> None:
    mission = create_mission(session)
    repository = ActionPlanRepository(session)

    def payload(title: str) -> ActionPlanCreate:
        return ActionPlanCreate(
            mission_id=mission.id,
            title=title,
            summary="Build and evaluate a recovery loop.",
            tasks_json=[
                ActionTask(
                    id="task-1",
                    title="Baseline",
                    description="Establish a baseline GUI agent.",
                    priority="high",
                    estimated_hours=4,
                    status="todo",
                )
            ],
            success_metrics_json=["Recovery success rate"],
            estimated_effort="5 days",
        )

    original = repository.save(payload("Original plan"))
    replacement = repository.save(payload("Updated plan"))

    assert replacement.id == original.id
    assert replacement.title == "Updated plan"
    assert replacement.tasks_json[0]["id"] == "task-1"


def test_agent_events_are_listed_in_creation_order(session: Session) -> None:
    mission = create_mission(session)
    repository = AgentEventRepository(session)
    for event_type in ("started", "completed"):
        repository.save(
            AgentEventCreate(
                mission_id=mission.id,
                agent_name="orchestrator",
                event_type=event_type,
                message=f"Mission {event_type}.",
                metadata={"iteration": 1},
            )
        )

    assert [event.event_type for event in repository.list_for_mission(mission.id)] == [
        "started",
        "completed",
    ]


def test_source_delete_cascades_to_evidence(session: Session) -> None:
    mission = create_mission(session)
    source = create_source(session, mission)
    create_evidence(session, mission, source)

    SourceDocumentRepository(session).delete(source)

    assert session.scalar(select(func.count()).select_from(EvidenceCard)) == 0


def test_mission_delete_cascades_all_children(session: Session) -> None:
    mission = create_mission(session)
    source = create_source(session, mission)
    evidence = create_evidence(session, mission, source)
    TechnologyOpportunityRepository(session).save(
        TechnologyOpportunityCreate(
            mission_id=mission.id,
            name="Self-Healing Agent",
            description="Recover from failed GUI actions.",
            related_evidence_ids_json=[evidence.id],
            novelty=4,
            technical_maturity=3,
            implementation_difficulty=3,
            goal_alignment=5,
            poc_feasibility=4,
            evidence_strength=4,
            overall_score=82,
            rationale="Strong one-week PoC candidate.",
        )
    )
    CoverageReportRepository(session).save(
        CoverageReportCreate(
            mission_id=mission.id,
            overall_score=80,
            sufficient=True,
            dimension_status_json={"novelty": "adequate"},
            iteration=1,
        )
    )
    ActionPlanRepository(session).save(
        ActionPlanCreate(
            mission_id=mission.id,
            title="PoC",
            summary="Build the recovery loop.",
            estimated_effort="5 days",
        )
    )
    AgentEventRepository(session).save(
        AgentEventCreate(
            mission_id=mission.id,
            agent_name="orchestrator",
            event_type="completed",
            message="Research complete.",
        )
    )

    ResearchMissionRepository(session).delete(mission)

    for model in (
        SourceDocument,
        EvidenceCard,
        TechnologyOpportunity,
        CoverageReport,
        ActionPlan,
        AgentEvent,
    ):
        assert session.scalar(select(func.count()).select_from(model)) == 0
