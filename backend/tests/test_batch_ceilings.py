"""Every batch a provider fills must have room above the working limit.

A schema bound set equal to the limit the application slices to fails a whole
round for holding items the next line would discard. That cost two live runs:
26 critique questions against a bound of 24, then 15 planned queries against a
bound of 12. Checking the schemas by hand is what let the second one through,
so the rule is asserted here across all of them at once.
"""

from inspect import signature

from pydantic import BaseModel

from app.agents.action import DEFAULT_MAX_TASKS, ActionAgent, _TaskPlan
from app.agents.analysis_llm import _DirectionBatch, _QuestionBatch
from app.agents.analyst import AnalystAgent
from app.agents.critic import CriticAgent
from app.agents.search import DEFAULT_MAX_QUERIES, SearchAgent, _QueryPlan


def ceiling(model: type[BaseModel], field: str) -> int:
    """Read the bound off the generated JSON Schema.

    That is the document the bound is actually enforced from, rather than the
    constant behind it, so a bound that never reached the schema is caught too.
    """

    limit = model.model_json_schema()["properties"][field].get("maxItems")
    assert limit is not None, f"{model.__name__}.{field} declares no maximum length"
    return limit


def default_of(agent: type, parameter: str) -> int:
    return signature(agent).parameters[parameter].default


BATCHES = [
    (
        _DirectionBatch,
        "directions",
        default_of(AnalystAgent, "max_generated_directions"),
    ),
    (_QuestionBatch, "questions", default_of(CriticAgent, "max_candidate_questions")),
    (_QueryPlan, "queries", default_of(SearchAgent, "max_queries")),
    (_QueryPlan, "repository_queries", DEFAULT_MAX_QUERIES),
    (_TaskPlan, "tasks", default_of(ActionAgent, "max_tasks")),
]


def test_every_provider_batch_has_room_above_its_working_limit() -> None:
    too_tight = [
        f"{model.__name__}.{field}: ceiling {ceiling(model, field)} "
        f"does not exceed the working limit {working}"
        for model, field, working in BATCHES
        if ceiling(model, field) <= working
    ]

    assert not too_tight, "; ".join(too_tight)


def test_the_defaults_this_rule_reads_still_exist() -> None:
    """Guards the guard: a renamed parameter would silently empty the table."""

    assert DEFAULT_MAX_QUERIES > 0
    assert DEFAULT_MAX_TASKS > 0
    assert len(BATCHES) == 5
