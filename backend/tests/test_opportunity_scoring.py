"""The arithmetic behind an opportunity score.

A 0–100 number reads as measurement, so every part of it that can be decided in
code is decided here rather than asked of a model.
"""

from uuid import uuid4

import pytest

from app.schemas.analysis import EvaluatedClaim, PocCandidate
from app.services.opportunity_scoring import (
    derive_evidence_strength,
    derive_poc_feasibility,
    evidence_agreement,
    overall_score,
    resolution_readiness,
    to_scale,
)

BEST = dict(
    novelty=5,
    goal_alignment=5,
    technical_maturity=5,
    poc_feasibility=5,
    evidence_strength=5,
    implementation_difficulty=1,
)


def claim(verdict: str, testability: float | None = 0.8) -> EvaluatedClaim:
    return EvaluatedClaim(
        direction_id="d1",
        claim_id=f"claim-{verdict}-{testability}",
        statement="A testable statement.",
        is_core=True,
        supporting_evidence_ids=[],
        support_strength=0.8,
        poc_testability=testability,
        verdict=verdict,
        resolution_status=(
            "fatal"
            if verdict == "refuted"
            else "resolved"
            if verdict == "supported"
            else "poc_testable"
            if testability is not None and testability >= 0.6
            else "research_gap"
        ),
        rationale="Measurable within a bounded PoC.",
    )


def candidate(coverage: float, claims: list[EvaluatedClaim]) -> PocCandidate:
    return PocCandidate(
        direction_id="d1",
        title="A direction",
        hypothesis="A hypothesis.",
        evidence_ids=[uuid4()],
        evidence_coverage=coverage,
        claim_assessments=claims,
    )


# ------------------------------------------------------------------ formula


def test_the_best_possible_case_reaches_exactly_one_hundred() -> None:
    """Reached by normalizing, not by clipping."""

    assert overall_score(**BEST) == 100.0


def test_weak_evidence_scales_the_whole_score_down() -> None:
    """The bug this guards: clipping once made confidence stop mattering."""

    weak = overall_score(**{**BEST, "evidence_strength": 1})

    assert weak == 20.0, "one fifth the confidence, one fifth the score"


def test_difficulty_divides_rather_than_subtracts() -> None:
    hard = overall_score(**{**BEST, "implementation_difficulty": 5})

    assert hard == 20.0


def test_every_dimension_moves_the_score() -> None:
    """No dimension may be silently ignored by the arithmetic."""

    for dimension in BEST:
        worse = 5 if dimension == "implementation_difficulty" else 1
        assert overall_score(**{**BEST, dimension: worse}) < 100.0, dimension


def test_the_score_stays_inside_the_contract_range() -> None:
    worst = overall_score(
        novelty=1,
        goal_alignment=1,
        technical_maturity=1,
        poc_feasibility=1,
        evidence_strength=1,
        implementation_difficulty=5,
    )

    assert 0 <= worst <= 100
    assert worst > 0, "nothing viable enough to be scored should read as zero"


def test_an_out_of_range_difficulty_is_rejected() -> None:
    with pytest.raises(ValueError):
        overall_score(**{**BEST, "implementation_difficulty": 0})


# --------------------------------------------------------------- derivation


def test_agreement_discounts_contested_and_unresolved_claims() -> None:
    assert evidence_agreement([claim("supported")]) == 1.0
    assert evidence_agreement([claim("contested")]) < 1.0
    assert evidence_agreement([claim("unknown")]) < 1.0
    assert evidence_agreement([claim("refuted")]) == 0.0


def test_a_resolvable_objection_costs_less_than_an_unresolvable_one() -> None:
    """Disagreement is discounted by how answerable it is, not by how loud.

    A contested claim a PoC can settle stays well ahead of one that needs more
    research, but it does not draw level with a claim the evidence already
    settles: this figure is the confidence term of the score, and a direction
    we can find out about is not one we already know about.
    """

    # One claim each: averaging several would halve the gap between them and
    # the five-bucket output scale would then round the distinction away.
    settled = candidate(0.9, [claim("supported")])
    answerable = candidate(0.9, [claim("contested", 0.9)])
    unanswerable = candidate(0.9, [claim("contested", 0.2)])

    assert evidence_agreement(settled.claim_assessments) > evidence_agreement(
        answerable.claim_assessments
    )
    readiness = resolution_readiness(answerable.claim_assessments)
    assert resolution_readiness(unanswerable.claim_assessments) < readiness < 1.0
    assert (
        derive_evidence_strength(unanswerable)
        < derive_evidence_strength(answerable)
        < derive_evidence_strength(settled)
    )


def test_an_unresolved_research_gap_still_reduces_readiness() -> None:
    ready = candidate(0.9, [claim("contested", 0.9)])
    needs_research = candidate(0.9, [claim("contested", 0.2)])

    assert resolution_readiness(ready.claim_assessments) > resolution_readiness(
        needs_research.claim_assessments
    )
    assert derive_evidence_strength(ready) > derive_evidence_strength(needs_research)


def test_feasibility_ignores_claims_the_reviewer_left_unscored() -> None:
    """Invariant 3: an unknown stays unknown, it does not become untestable."""

    scored_only = candidate(0.9, [claim("supported", 0.9)])
    with_unscored = candidate(0.9, [claim("supported", 0.9), claim("unknown", None)])

    assert derive_poc_feasibility(scored_only) == derive_poc_feasibility(with_unscored)


def test_a_candidate_with_no_scored_claim_is_least_feasible() -> None:
    assert derive_poc_feasibility(candidate(0.9, [claim("unknown", None)])) == 1


def test_the_unit_scale_maps_onto_one_through_five() -> None:
    assert to_scale(0.0) == 1
    assert to_scale(1.0) == 5
    assert to_scale(0.5) == 3
    assert to_scale(-1.0) == 1, "bounded rather than raising"
    assert to_scale(2.0) == 5
