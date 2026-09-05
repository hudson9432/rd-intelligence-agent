"""Action Agent: turns a PoC candidate into an executable task plan.

The plan is the last step of the product loop, and the one most likely to read
convincingly while meaning nothing. A generic checklist — "set up environment",
"run experiment", "write report" — fits any mission and settles none of them,
so the agent is built so that a task has to earn its place: it must name an
open item from the candidate, and a task naming nothing real is discarded.

The model writes the work; deterministic code owns the rest. Identifiers,
dependency resolution, effort aggregation, and the task ceiling are decided
here rather than by the model, which `AGENTS.md` requires of anything that
behaves like a business rule.
"""

from __future__ import annotations

import hashlib
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.llm import LLMClient, LLMStructuredOutputError
from app.prompts.action import build_action_messages
from app.schemas.action_plan import ActionPlanCreate, ActionTask
from app.schemas.analysis import PocCandidate
from app.schemas.workflow import WorkflowDecision

DEFAULT_MAX_TASKS = 8
MAX_GENERATED_TASKS = 12

# Separate from MAX_GENERATED_TASKS, which bounds what a caller may ask for.
# This one only rejects runaway output: the planner slices to its own limit.
TASK_BATCH_CEILING = 48
METRIC_BATCH_CEILING = 24
MAX_SUCCESS_METRICS = 6
TASK_STATUS_TODO = "todo"

#: Effort bands reported to the reader, longest first.
_EFFORT_BANDS: tuple[tuple[float, str], ...] = (
    (8.0, "about 1 day"),
    (24.0, "about 3 days"),
    (40.0, "about 1 week"),
    (80.0, "about 2 weeks"),
)
_EFFORT_BEYOND = "more than 2 weeks"


class ActionPlanningError(RuntimeError):
    """Raised when a provider cannot produce a usable task plan."""


class _PlannedTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    priority: Literal["high", "medium", "low"]
    estimated_hours: float = Field(gt=0, le=80)
    addresses: str = Field(min_length=1)
    depends_on: list[int] = Field(default_factory=list)


class _TaskPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1)
    tasks: list[_PlannedTask] = Field(min_length=1, max_length=TASK_BATCH_CEILING)
    success_metrics: list[str] = Field(min_length=1, max_length=METRIC_BATCH_CEILING)


class ActionAgent:
    """Plans the experiment that would settle a candidate's open questions."""

    def __init__(
        self, llm_client: LLMClient, *, max_tasks: int = DEFAULT_MAX_TASKS
    ) -> None:
        if not 1 <= max_tasks <= MAX_GENERATED_TASKS:
            raise ValueError(f"max_tasks must be between 1 and {MAX_GENERATED_TASKS}")
        self._llm_client = llm_client
        self._max_tasks = max_tasks

    def plan(
        self,
        *,
        mission_id: UUID,
        mission_goal: str,
        candidate: PocCandidate,
        decision: WorkflowDecision,
    ) -> ActionPlanCreate:
        open_items = open_items_for(candidate)
        if not open_items:
            raise ActionPlanningError(
                "The candidate records no claim or open question to test."
            )

        try:
            plan = self._llm_client.complete_structured(
                build_action_messages(
                    mission_goal=mission_goal,
                    candidate=candidate,
                    decision=decision,
                    open_items=open_items,
                ),
                _TaskPlan,
                mock_factory=lambda: _mock_task_plan(candidate, open_items),
            )
        except LLMStructuredOutputError as error:
            raise ActionPlanningError(
                "LLM response did not match the task-plan contract"
            ) from error

        important_questions = {
            item_id for item_id in open_items if item_id.startswith("question-")
        }
        tasks = _resolve_tasks(
            plan.tasks,
            open_items,
            required_items=important_questions,
            limit=self._max_tasks,
        )
        if not tasks:
            raise ActionPlanningError(
                "No planned task addressed an open item from the candidate."
            )

        return ActionPlanCreate(
            mission_id=mission_id,
            title=f"PoC: {candidate.title}"[:300],
            summary=plan.summary,
            tasks_json=tasks,
            success_metrics_json=plan.success_metrics[:MAX_SUCCESS_METRICS],
            estimated_effort=_effort_band(sum(task.estimated_hours for task in tasks)),
        )


def open_items_for(candidate: PocCandidate) -> dict[str, str]:
    """The things a PoC for this candidate would have to settle.

    Claims come first because they carry an identifier the model can echo back;
    reviewer questions are keyed by position so they can be cited the same way.
    """

    items = {
        assessment.claim_id: assessment.statement
        for assessment in candidate.claim_assessments
    }
    for index, question in enumerate(candidate.unresolved_questions, start=1):
        items[f"question-{index}"] = question
    return items


def _resolve_tasks(
    planned: list[_PlannedTask],
    open_items: dict[str, str],
    *,
    required_items: set[str],
    limit: int,
) -> list[ActionTask]:
    """Assign identifiers, keep only grounded tasks, and settle dependencies.

    A task may depend only on a task that came before it, so a dependency cycle
    cannot be expressed at all rather than having to be detected. References to
    a later task, to itself, or to a position that does not exist are dropped;
    the task survives without them, since a bad edge is not a reason to lose
    the work.
    """

    if len(required_items) > limit:
        raise ActionPlanningError(
            "The task ceiling cannot cover every important critique question."
        )

    grounded = [
        (position, task)
        for position, task in enumerate(planned, start=1)
        if task.addresses in open_items
    ]
    first_position_by_item: dict[str, int] = {}
    for position, task in grounded:
        first_position_by_item.setdefault(task.addresses, position)

    missing = sorted(required_items - first_position_by_item.keys())
    if missing:
        raise ActionPlanningError(
            "Planned tasks did not address every important critique question: "
            + ", ".join(missing)
        )

    selected_positions = {first_position_by_item[item_id] for item_id in required_items}
    for position, _task in grounded:
        if len(selected_positions) >= limit:
            break
        selected_positions.add(position)
    selected = [item for item in grounded if item[0] in selected_positions]
    identifiers_by_position = {
        position: f"task-{index}-{_digest(task.title, task.addresses)}"
        for index, (position, task) in enumerate(selected, start=1)
    }

    resolved: list[ActionTask] = []
    for position, task in selected:
        dependencies = [
            identifiers_by_position[reference]
            for reference in dict.fromkeys(task.depends_on)
            if reference < position and reference in identifiers_by_position
        ]
        resolved.append(
            ActionTask(
                id=identifiers_by_position[position],
                title=task.title,
                description=task.description,
                addresses=task.addresses,
                priority=task.priority,
                estimated_hours=task.estimated_hours,
                dependencies=dependencies,
                status=TASK_STATUS_TODO,
            )
        )
    return resolved


def _effort_band(total_hours: float) -> str:
    for ceiling, label in _EFFORT_BANDS:
        if total_hours <= ceiling:
            return label
    return _EFFORT_BEYOND


def _digest(*values: str) -> str:
    return hashlib.sha256("\n".join(values).encode("utf-8")).hexdigest()[:8]


def _mock_task_plan(candidate: PocCandidate, open_items: dict[str, str]) -> _TaskPlan:
    """Offline plan built only from text the candidate already contains.

    One task per open item, worded as the work of settling it. Nothing here is
    invented: the statement is copied, and the hours are a flat placeholder
    rather than an estimate the mock is in no position to make.
    """

    tasks = [
        _PlannedTask(
            title=f"Settle: {statement}"[:200],
            description=(
                f"Design and run the smallest experiment that decides "
                f"whether this holds: {statement}"
            ),
            priority="high" if item_id.startswith("question-") else "medium",
            estimated_hours=8,
            addresses=item_id,
            depends_on=[1] if index > 1 else [],
        )
        for index, (item_id, statement) in enumerate(open_items.items(), start=1)
    ][:MAX_GENERATED_TASKS]

    return _TaskPlan(
        summary=(
            f"Bounded proof of concept for {candidate.title}, testing whether "
            f"{candidate.hypothesis}"
        ),
        tasks=tasks,
        success_metrics=[
            f"Every open item is answered with recorded evidence: "
            f"{', '.join(list(open_items)[:MAX_SUCCESS_METRICS])}"
        ],
    )
