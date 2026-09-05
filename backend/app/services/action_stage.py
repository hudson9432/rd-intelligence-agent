"""Action planning wired as a workflow stage.

Phase 11. Turns the direction the Decision stage chose into the task plan the
mission ends with, satisfying the orchestrator's `ActionStage` protocol.

The stage picks the candidate rather than letting the agent choose: which
direction to build is the Decision stage's call, and an agent that reinterprets
that would quietly own a decision the product assigns elsewhere.
"""

from __future__ import annotations

from uuid import UUID

from app.agents.action import ActionAgent, ActionPlanningError
from app.agents.orchestrator import WorkflowStageError
from app.core.config import Settings, get_settings
from app.core.llm import LLMClient, LLMProviderError, get_llm_client
from app.schemas.action_plan import ActionPlanCreate
from app.schemas.analysis import PhaseCHandoff, PocCandidate
from app.schemas.workflow import WorkflowDecision


class PocActionStage:
    """Plans the PoC for the direction the decision selected."""

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        *,
        settings: Settings | None = None,
        mission_goal: str = "",
    ) -> None:
        self._agent = ActionAgent(
            llm_client or get_llm_client(settings or get_settings())
        )
        self._mission_goal = mission_goal

    def plan(
        self,
        *,
        mission_id: UUID,
        handoff: PhaseCHandoff,
        decision: WorkflowDecision,
    ) -> ActionPlanCreate | None:
        candidate = _selected_candidate(handoff, decision)
        if candidate is None:
            # The graph only routes here after a go decision, so this means the
            # decision named a direction the handoff does not carry. Planning
            # against a different candidate would silently substitute one.
            return None

        try:
            return self._agent.plan(
                mission_id=mission_id,
                mission_goal=self._mission_goal or candidate.title,
                candidate=candidate,
                decision=decision,
            )
        except LLMProviderError as error:
            raise WorkflowStageError(
                "The action provider request failed; no plan was made."
            ) from error
        except ActionPlanningError as error:
            raise WorkflowStageError(
                f"The action provider returned an unusable plan: {error}"
            ) from error


def _selected_candidate(
    handoff: PhaseCHandoff, decision: WorkflowDecision
) -> PocCandidate | None:
    for candidate in handoff.poc_candidates:
        if candidate.direction_id == decision.selected_direction_id:
            return candidate
    return None
