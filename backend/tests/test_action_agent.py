"""The Action Agent turns a PoC candidate into work that settles it.

The risk this file exists for is a plan that reads convincingly and means
nothing: "set up environment, run experiment, write report" fits every mission
and settles none. A task therefore has to name an open item the candidate
actually carries, and the checks below hold that line — including against a
provider that returns a plausible plan grounded in nothing.
"""

from uuid import uuid4

import pytest

from app.agents.action import (
    ActionAgent,
    ActionPlanningError,
    open_items_for,
)
from app.core.llm import LLMClient, MockLLMClient
from app.schemas.analysis import EvaluatedClaim, PocCandidate
from app.schemas.llm import LLMCompletion, LLMMessage
from app.schemas.workflow import WorkflowDecision

GOAL = "Decide whether quantized on-device inference suits our robotics line."


class ScriptedLLMClient(LLMClient):
    """Returns one fixed JSON body, as a live provider would."""

    model_name = "scripted"

    def __init__(self, content: str) -> None:
        self._content = content

    def complete(self, messages: list[LLMMessage]) -> LLMCompletion:
        del messages
        return LLMCompletion(content=self._content, model="scripted", mocked=False)


def claim(claim_id: str, statement: str, verdict: str = "supported") -> EvaluatedClaim:
    return EvaluatedClaim(
        direction_id="d1",
        claim_id=claim_id,
        statement=statement,
        is_core=True,
        supporting_evidence_ids=[],
        support_strength=0.8,
        poc_testability=0.9,
        verdict=verdict,
        rationale="Measurable within a bounded PoC.",
    )


def candidate(*, questions: list[str] | None = None) -> PocCandidate:
    return PocCandidate(
        direction_id="d1",
        title="Quantized on-device inference",
        hypothesis="A 4-bit model meets the latency budget on the target device.",
        evidence_ids=[uuid4()],
        evidence_coverage=0.8,
        claim_assessments=[claim("c1", "Latency stays under 50ms.")],
        unresolved_questions=questions
        if questions is not None
        else ["Does it hold on a second device class?"],
    )


def go_decision() -> WorkflowDecision:
    return WorkflowDecision(
        recommendation="proceed_with_poc",
        rationale="The direction is evidence-grounded.",
        selected_direction_id="d1",
    )


def plan_with(client: LLMClient, poc: PocCandidate | None = None, **kwargs):
    return ActionAgent(client, **kwargs).plan(
        mission_id=uuid4(),
        mission_goal=GOAL,
        candidate=poc or candidate(),
        decision=go_decision(),
    )


def scripted(tasks: str, metrics: str = '["Latency is recorded on both devices."]'):
    return ScriptedLLMClient(
        '{"summary":"Bounded PoC.","tasks":'
        + tasks
        + ',"success_metrics":'
        + metrics
        + "}"
    )


def task_json(addresses: str, *, title: str = "Measure latency", depends: str = "[]"):
    return (
        '{"title":"' + title + '","description":"Run the measurement.",'
        '"priority":"high","estimated_hours":8,"addresses":"' + addresses + '",'
        '"depends_on":' + depends + "}"
    )


# ------------------------------------------------------------- open items


def test_open_items_cover_claims_and_reviewer_questions() -> None:
    items = open_items_for(candidate(questions=["First?", "Second?"]))

    assert items["c1"] == "Latency stays under 50ms."
    assert items["question-1"] == "First?"
    assert items["question-2"] == "Second?"


def test_a_candidate_with_no_open_item_cannot_be_planned() -> None:
    """Nothing to settle means there is no proof of concept to run."""

    empty = candidate().model_copy(
        update={"claim_assessments": [], "unresolved_questions": []}
    )

    with pytest.raises(ActionPlanningError, match="no claim or open question"):
        plan_with(MockLLMClient(), empty)


# --------------------------------------------------------------- grounding


def test_a_task_addressing_nothing_real_is_discarded() -> None:
    """The guard against a plausible plan grounded in nothing."""

    client = scripted(
        "["
        + task_json("c1", title="Measure latency")
        + ","
        + task_json("invented-item", title="Improve overall quality")
        + "]"
    )

    plan = plan_with(client)

    assert [task.title for task in plan.tasks_json] == ["Measure latency"]


def test_a_plan_grounded_in_nothing_at_all_fails() -> None:
    client = scripted("[" + task_json("invented-item") + "]")

    with pytest.raises(ActionPlanningError, match="addressed an open item"):
        plan_with(client)


def test_a_reviewer_question_can_be_addressed_by_position() -> None:
    client = scripted("[" + task_json("question-1", title="Test second device") + "]")

    plan = plan_with(client)

    assert [task.title for task in plan.tasks_json] == ["Test second device"]


# ------------------------------------------------------------ dependencies


def test_a_task_may_depend_only_on_an_earlier_task() -> None:
    """Cycles are made unrepresentable rather than detected."""

    client = scripted(
        "["
        + task_json("c1", title="First", depends="[2]")
        + ","
        + task_json("question-1", title="Second", depends="[1]")
        + "]"
    )

    plan = plan_with(client)

    first, second = plan.tasks_json
    assert first.dependencies == [], "a forward reference is dropped"
    assert second.dependencies == [first.id]


def test_a_self_reference_and_an_unknown_position_are_dropped() -> None:
    client = scripted("[" + task_json("c1", depends="[1, 9]") + "]")

    plan = plan_with(client)

    assert plan.tasks_json[0].dependencies == []


def test_a_bad_dependency_does_not_lose_the_task() -> None:
    client = scripted("[" + task_json("c1", title="Keep me", depends="[7]") + "]")

    plan = plan_with(client)

    assert [task.title for task in plan.tasks_json] == ["Keep me"]


# ------------------------------------------------------ deterministic rules


def test_effort_is_computed_from_the_tasks_not_supplied() -> None:
    client = scripted("[" + task_json("c1") + "," + task_json("question-1") + "]")

    plan = plan_with(client)

    # Two eight-hour tasks fall in the three-day band.
    assert plan.estimated_effort == "about 3 days"


def test_task_identifiers_are_assigned_here_and_are_unique() -> None:
    client = scripted(
        "["
        + task_json("c1", title="Same title")
        + ","
        + task_json("question-1", title="Same title")
        + "]"
    )

    plan = plan_with(client)

    identifiers = [task.id for task in plan.tasks_json]
    assert len(set(identifiers)) == 2
    assert all(task.status == "todo" for task in plan.tasks_json)


def test_the_task_ceiling_is_enforced_here() -> None:
    poc = candidate(questions=[f"Question {index}?" for index in range(1, 6)])
    tasks = ",".join(
        task_json(item, title=f"Task {index}")
        for index, item in enumerate(open_items_for(poc), start=1)
    )

    plan = plan_with(scripted("[" + tasks + "]"), poc, max_tasks=2)

    assert len(plan.tasks_json) == 2


def test_an_unusable_provider_response_fails_the_plan() -> None:
    with pytest.raises(ActionPlanningError, match="task-plan contract"):
        plan_with(ScriptedLLMClient("not json at all"))


# ------------------------------------------------------------ offline plan


def test_the_offline_plan_invents_nothing() -> None:
    """Every word of the mock plan traces to the candidate."""

    poc = candidate(questions=["Does it hold on a second device class?"])

    plan = plan_with(MockLLMClient(), poc)

    assert len(plan.tasks_json) == len(open_items_for(poc))
    corpus = poc.hypothesis + poc.title + " ".join(open_items_for(poc).values())
    for task in plan.tasks_json:
        settled = task.title.removeprefix("Settle: ")
        assert settled[:40] in corpus, "the mock must copy, not compose"


def test_the_offline_plan_is_deterministic() -> None:
    poc = candidate()

    first = plan_with(MockLLMClient(), poc)
    second = plan_with(MockLLMClient(), poc)

    assert [task.title for task in first.tasks_json] == [
        task.title for task in second.tasks_json
    ]
    assert first.estimated_effort == second.estimated_effort
