"""Every list a provider fills must have room above the limit code slices to.

A bound set equal to that limit fails a whole round for holding items the next
line discards. It has cost three runs so far: 26 critique questions against 24,
15 planned queries against 12, and 7 success metrics against 6. The first of
those ended a fourteen-minute run outright.

Each of those was found by a live failure because the previous fix checked the
remaining schemas by hand. So the bounds are discovered here instead: every
model a provider fills is walked, nested definitions included, and a bound that
nobody has recorded a working limit for fails the suite rather than waiting to
be found in production.
"""

from typing import Any

from pydantic import BaseModel

from app.agents.action import (
    DEFAULT_MAX_TASKS,
    MAX_SUCCESS_METRICS,
    _TaskPlan,
)
from app.agents.analysis_llm import _ClaimReviewBatch, _DirectionBatch, _QuestionBatch
from app.agents.decision import _CandidateRating
from app.agents.evidence import EvidenceExtraction
from app.agents.search import DEFAULT_MAX_QUERIES, _QueryPlan
from app.schemas.analysis import CritiqueQuestionDraft, SemanticQuestionScores

#: Every model handed to ``complete_structured``. A new structured call belongs
#: here, or its bounds go unchecked.
PROVIDER_FILLED_MODELS: tuple[type[BaseModel], ...] = (
    _CandidateRating,
    _ClaimReviewBatch,
    _DirectionBatch,
    _QuestionBatch,
    _QueryPlan,
    _TaskPlan,
    CritiqueQuestionDraft,
    EvidenceExtraction,
    SemanticQuestionScores,
)

#: Bound -> the limit application code slices that list to. Recording one is a
#: statement that the pair has been looked at; the ceiling must exceed it.
WORKING_LIMITS: dict[str, int] = {
    "_DirectionBatch.directions": 12,
    "_QuestionBatch.questions": 24,
    "_QueryPlan.queries": DEFAULT_MAX_QUERIES,
    "_QueryPlan.repository_queries": DEFAULT_MAX_QUERIES,
    "_TaskPlan.tasks": DEFAULT_MAX_TASKS,
    "_TaskPlan.success_metrics": MAX_SUCCESS_METRICS,
}


def bounded_list_fields() -> dict[str, int]:
    """Find every ``maxItems`` a provider could run into, nested ones included."""

    found: dict[str, int] = {}
    for model in PROVIDER_FILLED_MODELS:
        schema = model.model_json_schema()
        blocks: list[tuple[str, dict[str, Any]]] = [(model.__name__, schema)]
        blocks += list((schema.get("$defs") or {}).items())
        for owner, body in blocks:
            for field, spec in (body.get("properties") or {}).items():
                limit = spec.get("maxItems")
                if limit is not None:
                    found[f"{owner}.{field}"] = limit
    return found


def test_every_bound_has_room_above_the_limit_code_slices_to() -> None:
    too_tight = {
        name: (ceiling, WORKING_LIMITS[name])
        for name, ceiling in bounded_list_fields().items()
        if name in WORKING_LIMITS and ceiling <= WORKING_LIMITS[name]
    }

    assert not too_tight, (
        "these bounds sit on the limit their own code slices to, so a batch one "
        f"item over fails the round for nothing: {too_tight}"
    )


def test_no_bound_escapes_review() -> None:
    """Discovery is the point: a new bound must be looked at, not inherited."""

    unreviewed = sorted(set(bounded_list_fields()) - set(WORKING_LIMITS))

    assert not unreviewed, (
        "a provider-filled list gained a maximum with no recorded working "
        f"limit; add it to WORKING_LIMITS once checked: {unreviewed}"
    )


def test_no_reviewed_bound_has_quietly_disappeared() -> None:
    """A rename would otherwise leave this file agreeing with nothing."""

    stale = sorted(set(WORKING_LIMITS) - set(bounded_list_fields()))

    assert not stale, f"WORKING_LIMITS names bounds that no longer exist: {stale}"
