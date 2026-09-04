"""Mission workflow application service.

Owns everything the orchestrator deliberately does not: loading the mission,
persisting each stage transition as an `AgentEvent`, storing a produced action
plan, and moving mission status through `running` to a terminal state.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from uuid import UUID

from sqlalchemy.orm import Session

from app.agents.orchestrator import WorkflowOrchestrator, WorkflowStages
from app.agents.pending_stages import PendingActionStage, PendingDecisionStage
from app.core.config import Settings, get_settings
from app.core.llm import LLMClient, get_llm_client
from app.repositories.action_plan import ActionPlanRepository
from app.repositories.agent_event import AgentEventRepository
from app.schemas.agent_event import AgentEventCreate
from app.schemas.research_mission import MissionStatus, ResearchMissionUpdate
from app.schemas.workflow import WorkflowEvent, WorkflowRunResult, WorkflowState
from app.services.analysis_stage import PhaseCAnalysisStage
from app.services.evidence_stage import PersistingEvidenceStage
from app.services.mission import MissionService
from app.services.search_stage import ResearchSourceSearchStage

DEFAULT_MAX_ITERATIONS = 2

logger = logging.getLogger(__name__)


class WorkflowAlreadyRunningError(RuntimeError):
    """Raised when a mission workflow is started while one is in progress."""

    def __init__(self, mission_id: UUID | str) -> None:
        self.mission_id = str(mission_id)
        super().__init__(f"Mission {self.mission_id} is already running")


def default_stages(
    session: Session,
    *,
    llm_client: LLMClient | None = None,
    settings: Settings | None = None,
) -> WorkflowStages:
    """The current stage set.

    Search, Evidence, and Analysis are real. Decision and Action are still
    placeholders; see `app.agents.pending_stages` for what each does and does
    not do.

    The search stage is built per call because it remembers which sources a
    run has already seen, which must not leak between missions.
    """

    resolved_settings = settings or get_settings()
    shared_llm_client = llm_client or get_llm_client(resolved_settings)

    return WorkflowStages(
        search=ResearchSourceSearchStage(
            llm_client=shared_llm_client,
            settings=resolved_settings,
        ),
        evidence=PersistingEvidenceStage(
            session,
            llm_client=shared_llm_client,
            settings=resolved_settings,
        ),
        analysis=PhaseCAnalysisStage(
            shared_llm_client,
            settings=resolved_settings,
        ),
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
        self.stages = stages if stages is not None else default_stages(session)
        self.max_iterations = max_iterations

    def claim_run(self, mission_id: UUID | str) -> str:
        """Mark a mission running before synchronous or background execution."""

        mission = self.missions.get(mission_id)
        if mission.status == MissionStatus.RUNNING:
            raise WorkflowAlreadyRunningError(mission.id)

        self.missions.update(
            mission.id, ResearchMissionUpdate(status=MissionStatus.RUNNING)
        )
        return mission.id

    def run(self, mission_id: UUID | str) -> WorkflowRunResult:
        """Claim and run a workflow synchronously to a terminal state."""

        claimed_id = self.claim_run(mission_id)
        try:
            return self.run_claimed(claimed_id)
        except Exception:
            # Known stage failures become WorkflowRunResult values. This guard
            # covers unexpected faults so a synchronous caller cannot strand
            # the mission in RUNNING forever.
            self.missions.update(
                claimed_id,
                ResearchMissionUpdate(status=MissionStatus.FAILED),
            )
            raise

    def run_claimed(self, mission_id: UUID | str) -> WorkflowRunResult:
        """Run a mission already claimed by a background request."""

        mission = self.missions.get(mission_id)
        if mission.status != MissionStatus.RUNNING:
            raise RuntimeError(
                f"Mission {mission.id} must be running before execution starts"
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


def run_workflow_in_background(
    mission_id: UUID | str,
    *,
    session_factory: Callable[[], Session] | None = None,
) -> None:
    """Execute a claimed mission with a session independent of the HTTP request."""

    if session_factory is None:
        # Imported lazily to avoid coupling module import to the global engine
        # when tests inject their own isolated session factory.
        from app.db.session import SessionLocal

        session_factory = SessionLocal

    with session_factory() as session:
        try:
            WorkflowService(session).run_claimed(mission_id)
        except Exception as error:  # background boundary must never strand RUNNING
            logger.exception("Background workflow execution failed")
            session.rollback()
            try:
                mission = MissionService(session).get(mission_id)
                MissionService(session).update(
                    mission.id,
                    ResearchMissionUpdate(status=MissionStatus.FAILED),
                )
                AgentEventRepository(session).save(
                    AgentEventCreate(
                        mission_id=UUID(mission.id),
                        agent_name="orchestrator",
                        event_type="workflow_failed",
                        message=(
                            "Workflow stopped before the background worker could "
                            "produce a result."
                        ),
                        metadata={
                            "failed_stage": "startup",
                            "error_type": type(error).__name__,
                        },
                    )
                )
            except Exception:
                logger.exception("Could not persist background workflow failure")
