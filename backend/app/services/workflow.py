"""Mission workflow application service.

Owns everything the orchestrator deliberately does not: loading the mission,
persisting each stage transition as an `AgentEvent`, storing a produced action
plan, and moving mission status through `running` to a terminal state.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.agents.orchestrator import WorkflowOrchestrator, WorkflowStages
from app.agents.pending_stages import (
    PendingActionStage,
    PendingAnalysisStage,
    PendingDecisionStage,
    PendingEvidenceStage,
    PendingSearchStage,
)
from app.repositories.action_plan import ActionPlanRepository
from app.repositories.agent_event import AgentEventRepository
from app.schemas.agent_event import AgentEventCreate
from app.schemas.research_mission import MissionStatus, ResearchMissionUpdate
from app.schemas.workflow import WorkflowEvent, WorkflowRunResult, WorkflowState
from app.services.mission import MissionService

DEFAULT_MAX_ITERATIONS = 2


class WorkflowAlreadyRunningError(RuntimeError):
    """Raised when a mission workflow is started while one is in progress."""

    def __init__(self, mission_id: UUID | str) -> None:
        self.mission_id = str(mission_id)
        super().__init__(f"Mission {self.mission_id} is already running")


def default_stages() -> WorkflowStages:
    """The stage set for phases that have not landed yet.

    Every stage here is a placeholder; see `app.agents.pending_stages` for what
    each one does and does not do.
    """

    return WorkflowStages(
        search=PendingSearchStage(),
        evidence=PendingEvidenceStage(),
        analysis=PendingAnalysisStage(),
        decision=PendingDecisionStage(),
        action=PendingActionStage(),
    )


class WorkflowService:
    def __init__(
        self,
        session: Session,
        *,
        stages: WorkflowStages | None = None,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
    ) -> None:
        self.missions = MissionService(session)
        self.events = AgentEventRepository(session)
        self.action_plans = ActionPlanRepository(session)
        self.stages = stages if stages is not None else default_stages()
        self.max_iterations = max_iterations

    def run(self, mission_id: UUID | str) -> WorkflowRunResult:
        """Run the workflow to a terminal state, persisting progress as it goes.

        Raises `MissionNotFoundError` for an unknown mission and
        `WorkflowAlreadyRunningError` if one is already in progress.
        """

        mission = self.missions.get(mission_id)
        if mission.status == MissionStatus.RUNNING:
            raise WorkflowAlreadyRunningError(mission.id)

        self.missions.update(
            mission.id, ResearchMissionUpdate(status=MissionStatus.RUNNING)
        )

        state = WorkflowState(
            mission_id=UUID(mission.id),
            goal=mission.goal,
            max_iterations=self.max_iterations,
        )

        def persist(event: WorkflowEvent) -> None:
            # Committed one at a time so a client polling
            # `GET /missions/{id}/events` sees progress while the run is live.
            self.events.save(
                AgentEventCreate(
                    mission_id=UUID(mission.id),
                    agent_name=event.agent_name,
                    event_type=event.event_type,
                    message=event.message,
                    metadata=event.metadata,
                )
            )

        result = WorkflowOrchestrator(self.stages).run(state, on_event=persist)

        if result.action_plan is not None:
            self.action_plans.save(result.action_plan)

        self.missions.update(
            mission.id,
            ResearchMissionUpdate(
                status=(
                    MissionStatus.COMPLETED
                    if result.status == "completed"
                    else MissionStatus.FAILED
                )
            ),
        )
        return result
