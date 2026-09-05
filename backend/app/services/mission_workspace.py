"""Compose persisted mission data without invoking agents or external providers."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.repositories.action_plan import ActionPlanRepository
from app.repositories.evidence_card import EvidenceCardRepository
from app.repositories.source_document import SourceDocumentRepository
from app.repositories.technology_opportunity import TechnologyOpportunityRepository
from app.schemas.mission_workspace import MissionRunSummary, MissionWorkspace
from app.services.mission import MissionService


class MissionWorkspaceService:
    def __init__(self, session: Session) -> None:
        self.missions = MissionService(session)
        self.sources = SourceDocumentRepository(session)
        self.evidence = EvidenceCardRepository(session)
        self.opportunities = TechnologyOpportunityRepository(session)
        self.plans = ActionPlanRepository(session)

    def get(self, mission_id: UUID | str) -> MissionWorkspace:
        mission = self.missions.get(mission_id)
        events = self.missions.list_events(mission_id)
        starts = [event for event in events if event.event_type == "workflow_started"]
        started = starts[-1].created_at if starts else None
        # claim_run updates mission.updated_at before the worker emits its start.
        # During that window the entire previous event history is historical.
        if mission.status == "running" and (started is None or started < mission.updated_at):
            started = mission.updated_at
        current = [event for event in events if started and event.created_at >= started]
        terminals = [event for event in current if event.event_type in {"workflow_completed", "workflow_failed"}]
        terminal = terminals[-1] if terminals else None
        summary = None
        plan = None
        opportunities = []
        if mission.status == "completed" and terminal and terminal.event_type == "workflow_completed":
            summary = MissionRunSummary.model_validate(terminal.metadata_json)
            opportunities = [
                item for item in self.opportunities.list_for_mission(mission_id)
                if started and item.created_at >= started
            ]
            if summary.decision and summary.decision.recommendation == "proceed_with_poc" and any(
                event.event_type == "action_plan_created" for event in current
            ):
                plan = self.plans.get_for_mission(mission_id)
        failure = next((event for event in reversed(current) if event.event_type == "workflow_failed"), None)
        return MissionWorkspace(
            mission=mission,
            sources=self.sources.list_for_mission(mission_id),
            evidence=self.evidence.list_for_mission(mission_id),
            opportunities=opportunities,
            events=events,
            run_started_at=started,
            summary=summary,
            action_plan=plan,
            error=(failure.message if failure else "Workflow failed before producing a result.")
            if mission.status == "failed" else None,
        )
