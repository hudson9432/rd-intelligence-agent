"""The Action stage plans for the direction the Decision stage chose.

Which direction to build is the Decision stage's call. An Action stage that
reinterpreted it — planning for whichever candidate looked best — would quietly
own a decision the product assigns elsewhere, so the selection is matched by id
and a mismatch produces no plan rather than a substituted one.
"""

from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.agents.orchestrator import WorkflowStageError
from app.core.llm import LLMClient, MockLLMClient
from app.repositories.action_plan import ActionPlanRepository
from app.schemas.analysis import PhaseCHandoff
from app.schemas.llm import LLMCompletion, LLMMessage
from app.schemas.research_mission import MissionStatus, ResearchMissionCreate
from app.services.action_stage import PocActionStage
from app.services.mission import MissionService
from app.services.workflow import WorkflowService
from tests.test_action_agent import candidate, go_decision

GOAL = "Decide whether quantized on-device inference suits our robotics line."


class BrokenLLMClient(LLMClient):
    model_name = "broken"

    def complete(self, messages: list[LLMMessage]) -> LLMCompletion:
        del messages
        return LLMCompletion(content="not json", model="broken", mocked=False)


def handoff_with(*direction_ids: str) -> PhaseCHandoff:
    return PhaseCHandoff(
        status="ready_for_poc",
        reason="A direction is testable.",
        poc_candidates=[
            candidate().model_copy(update={"direction_id": direction_id})
            for direction_id in direction_ids
        ],
    )


def stage(client: LLMClient | None = None) -> PocActionStage:
    return PocActionStage(client or MockLLMClient(), mission_goal=GOAL)


def test_it_plans_for_the_direction_the_decision_selected() -> None:
    handoff = handoff_with("other", "d1")

    plan = stage().plan(mission_id=uuid4(), handoff=handoff, decision=go_decision())

    assert plan is not None
    assert plan.tasks_json


def test_a_decision_naming_a_missing_direction_produces_no_plan() -> None:
    """Substituting a different candidate would swap the decision silently."""

    handoff = handoff_with("something-else")

    plan = stage().plan(mission_id=uuid4(), handoff=handoff, decision=go_decision())

    assert plan is None


def test_an_unusable_provider_response_fails_the_stage() -> None:
    with pytest.raises(WorkflowStageError, match="unusable plan"):
        stage(BrokenLLMClient()).plan(
            mission_id=uuid4(), handoff=handoff_with("d1"), decision=go_decision()
        )


def test_the_plan_belongs_to_the_mission_that_asked_for_it() -> None:
    mission_id = uuid4()

    plan = stage().plan(
        mission_id=mission_id, handoff=handoff_with("d1"), decision=go_decision()
    )

    assert plan is not None
    assert plan.mission_id == mission_id


def test_a_completed_mission_stores_its_plan(session: Session) -> None:
    """End to end: the run reaches a persisted plan, not just a candidate."""

    mission = MissionService(session).create(
        ResearchMissionCreate(
            title="RAG",
            goal="Decide whether retrieval augmented generation is reliable enough.",
        )
    )

    result = WorkflowService(session, max_iterations=2).run(mission.id)

    assert result.status == "completed"
    assert result.action_plan is not None, result.error
    stored = ActionPlanRepository(session).get_for_mission(UUID(mission.id))
    assert stored is not None
    assert stored.tasks_json, "a stored plan with no task settles nothing"
    assert stored.estimated_effort
    assert MissionService(session).get(mission.id).status == MissionStatus.COMPLETED


def test_the_run_reports_the_plan_as_an_event(session: Session) -> None:
    mission = MissionService(session).create(
        ResearchMissionCreate(
            title="RAG",
            goal="Decide whether retrieval augmented generation is reliable enough.",
        )
    )

    result = WorkflowService(session, max_iterations=2).run(mission.id)

    created = [
        event for event in result.events if event.event_type == "action_plan_created"
    ]
    assert created, "the mission must end by reporting the plan it produced"
    assert created[0].metadata["task_count"] > 0
