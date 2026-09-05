"""Deterministic parts of opportunity scoring.

Two of the six dimensions are derived from what Phase C already established
rather than asked of a model, and the combining formula lives here rather than
in a prompt: `AGENTS.md` requires that scoring and routing stay in
deterministic, typed code.

The formula's shape is borrowed rather than invented. RICE — Intercom's
prioritisation model, `(Reach × Impact × Confidence) / Effort` — supplies the
structural point that confidence multiplies and effort divides. Weak evidence
should scale an assessment down proportionally rather than subtract a fixed
amount from it, and difficulty is a cost to divide by, not a penalty to
subtract. The grouping into benefit, readiness, confidence, and cost follows
the reward-versus-risk split used by stage-gate scorecards.

What is *not* borrowed: the weighting inside each group is flat. There is no
evidence that novelty should outrank goal alignment, and inventing a precise
weight vector would manufacture exactly the false precision this scoring is
supposed to avoid. Flat is an honest starting point, to be revised when real
use says otherwise.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.schemas.analysis import EvaluatedClaim, PocCandidate

SCALE_MAX = 5

#: How much a verdict says the body of evidence agrees with itself. Strength is
#: not only "how good is each card" but "do they tell the same story", and a
#: contested or unresolved claim should not score like a settled one.
_VERDICT_AGREEMENT: dict[str, float] = {
    "supported": 1.0,
    "contested": 0.6,
    "unknown": 0.7,
    "refuted": 0.0,
}

#: Whether an objection prevents the team from acting. A contested claim that
#: can be settled by the PoC is work to schedule, not evidence that the
#: opportunity is intrinsically worse.
_RESOLUTION_READINESS: dict[str, float] = {
    "resolved": 1.0,
    "poc_testable": 1.0,
    "research_gap": 0.7,
    "fatal": 0.0,
}


def to_scale(unit_value: float) -> int:
    """Map a 0–1 score onto the 1–5 scale the opportunity record uses.

    Linear across the whole range: 0 lands on 1, 0.5 on 3, and 1 on 5. Scaling
    by five and clamping instead would fold 0 and 0.25 both onto 1, losing a
    grade at the bottom, and would put the midpoint on 2 because Python rounds
    a half to even.
    """

    bounded = min(max(unit_value, 0.0), 1.0)
    return round(1 + bounded * (SCALE_MAX - 1))


def evidence_agreement(assessments: Sequence[EvaluatedClaim]) -> float:
    """Diagnostic consistency only; this no longer penalizes opportunity value."""

    if not assessments:
        return 0.0
    return sum(
        _VERDICT_AGREEMENT.get(assessment.verdict, 0.0) for assessment in assessments
    ) / len(assessments)


def resolution_readiness(assessments: Sequence[EvaluatedClaim]) -> float:
    """How much claim uncertainty is resolved or assigned to a bounded PoC."""

    if not assessments:
        return 0.0
    return sum(
        _RESOLUTION_READINESS.get(assessment.resolution_status, 0.0)
        for assessment in assessments
    ) / len(assessments)


def derive_evidence_strength(candidate: PocCandidate) -> int:
    """Coverage, discounted only when an objection cannot yet be handled.

    Evidence disagreement remains available through ``evidence_agreement`` as
    an audit diagnostic. It does not lower this opportunity score when the
    disagreement is explicitly assigned to a bounded PoC.
    """

    return to_scale(
        candidate.evidence_coverage * resolution_readiness(candidate.claim_assessments)
    )


def derive_poc_feasibility(candidate: PocCandidate) -> int:
    """How testable the claims are, as the reviewer already judged them.

    Claims the reviewer left unscored are ignored rather than counted as
    untestable: invariant 3 keeps an unknown unknown.
    """

    scored = [
        assessment.poc_testability
        for assessment in candidate.claim_assessments
        if assessment.poc_testability is not None
    ]
    if not scored:
        return 1
    return to_scale(sum(scored) / len(scored))


def overall_score(
    *,
    novelty: int,
    goal_alignment: int,
    technical_maturity: int,
    poc_feasibility: int,
    evidence_strength: int,
    implementation_difficulty: int,
) -> float:
    """Combine the six dimensions into a 0–100 score.

        merit      = mean(benefit, readiness) / 5    where
                       benefit   = mean(novelty, goal_alignment)
                       readiness = mean(technical_maturity, poc_feasibility)
        confidence = evidence_strength / 5           (multiplies, per RICE)
        effort     = implementation_difficulty       (divides, per RICE)

        score = 100 × merit × confidence / effort

    Normalized so that 100 is reached exactly — every dimension at its best
    with difficulty at 1 — rather than by clipping. That matters: an earlier
    version divided by a constant, so the raw value ran past 1 and got clamped,
    and the confidence multiplier stopped affecting the result at all. A
    candidate with worthless evidence scored the same as one with excellent
    evidence.

    Read the number as merit *per unit of difficulty*, not as a percentage of
    anything. Ratios compress: middling scores everywhere with middling
    difficulty lands near 12, not near 50. That is the formula working, but it
    means the score belongs beside the six dimensions rather than instead of
    them, and it is meaningful mainly for ranking candidates against each
    other.
    """

    if not 1 <= implementation_difficulty <= SCALE_MAX:
        raise ValueError("implementation_difficulty must be between 1 and 5")

    benefit = (novelty + goal_alignment) / 2
    readiness = (technical_maturity + poc_feasibility) / 2
    merit = ((benefit + readiness) / 2) / SCALE_MAX
    confidence = evidence_strength / SCALE_MAX

    score = 100 * merit * confidence / implementation_difficulty
    return round(min(max(score, 0.0), 100.0), 2)
