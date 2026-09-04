"""Final Phase C gate between analysis/critique and D's orchestration."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from app.schemas.analysis import (
    AnalystOutcome,
    ClaimReview,
    ClaimVerdict,
    CriticOutcome,
    EvaluatedClaim,
    PhaseCHandoff,
    PocCandidate,
    RankedDirection,
    TargetedResearchRequest,
)
from app.schemas.evidence_card import EvidenceCard
from app.services.scoring import evidence_index, evidence_strength


def build_phase_c_handoff(
    *,
    mission_goal: str,
    analysis: AnalystOutcome,
    critique: CriticOutcome,
    evidence: Sequence[EvidenceCard],
    claim_reviews: Sequence[ClaimReview],
    research_exhausted: bool = False,
    minimum_claim_support: float = 0.4,
    minimum_poc_testability: float = 0.6,
    strong_counterevidence: float = 0.7,
) -> PhaseCHandoff:
    """Judge claims and return research, PoC candidates, or no viable result.

    Missing evidence never becomes counterevidence. A direction is PoC-ready
    when at least one core claim has minimum support and is testable, no core
    claim is strongly refuted, and every unresolved core claim can be tested by
    the PoC. If no direction qualifies, re-search happens before No-PoC.
    """

    if not mission_goal.strip():
        raise ValueError("mission_goal cannot be empty")
    for name, value in (
        ("minimum_claim_support", minimum_claim_support),
        ("minimum_poc_testability", minimum_poc_testability),
        ("strong_counterevidence", strong_counterevidence),
    ):
        if not 0 <= value <= 1:
            raise ValueError(f"{name} must be between zero and one")

    if analysis.status != "ready":
        return _research_or_no_viable(
            research_exhausted=research_exhausted,
            request=critique.research_request
            or TargetedResearchRequest(
                queries=[mission_goal.strip()],
                reason="No evidence-backed direction has been generated.",
            ),
            reason="No evidence-backed direction has been generated.",
        )

    if critique.status == "research_required":
        assert critique.research_request is not None
        return _research_or_no_viable(
            research_exhausted=research_exhausted,
            request=critique.research_request,
            reason="Material critique questions still require evidence.",
        )

    evidence_by_id = evidence_index(evidence)
    assessments = _evaluate_claims(
        directions=analysis.active_directions,
        evidence_by_id=evidence_by_id,
        reviews=claim_reviews,
        strong_counterevidence=strong_counterevidence,
    )
    assessments_by_direction: dict[str, list[EvaluatedClaim]] = {}
    for assessment in assessments:
        assessments_by_direction.setdefault(assessment.direction_id, []).append(
            assessment
        )

    eligible = [
        direction
        for direction in analysis.active_directions
        if _is_poc_viable(
            assessments_by_direction.get(direction.id, []),
            minimum_claim_support=minimum_claim_support,
            minimum_poc_testability=minimum_poc_testability,
        )
    ]
    if not eligible:
        request = _claim_research_request(
            mission_goal=mission_goal,
            directions=analysis.active_directions,
            assessments=assessments,
            minimum_claim_support=minimum_claim_support,
            minimum_poc_testability=minimum_poc_testability,
        )
        return _research_or_no_viable(
            research_exhausted=research_exhausted,
            request=request,
            reason=(
                "No direction has a minimally supported, non-refuted, and "
                "PoC-testable core claim."
            ),
            claim_assessments=assessments,
        )

    return PhaseCHandoff(
        status="ready_for_poc",
        poc_candidates=[
            _poc_candidate(
                direction=direction,
                critique=critique,
                assessments=assessments_by_direction[direction.id],
            )
            for direction in eligible
        ],
        claim_assessments=assessments,
        reason=(
            "At least one direction has a minimally supported core hypothesis, "
            "no fatal counterevidence, and PoC-testable remaining uncertainty."
        ),
    )


def classify_claim_verdict(
    *,
    support_strength: float,
    counterevidence_strength: float | None,
    strong_counterevidence: float = 0.7,
) -> ClaimVerdict:
    """Classify evidence without treating unknown support as a negative."""

    if counterevidence_strength is None:
        return "unknown"
    if (
        counterevidence_strength >= strong_counterevidence
        and counterevidence_strength >= support_strength + 0.15
    ):
        return "refuted"
    if support_strength >= 0.6 and counterevidence_strength < 0.4:
        return "supported"
    if support_strength >= 0.4 and counterevidence_strength >= 0.4:
        return "contested"
    return "unknown"


def _evaluate_claims(
    *,
    directions: Sequence[RankedDirection],
    evidence_by_id: dict[UUID, EvidenceCard],
    reviews: Sequence[ClaimReview],
    strong_counterevidence: float,
) -> list[EvaluatedClaim]:
    review_by_key = {
        (review.direction_id, review.claim_id): review for review in reviews
    }
    if len(review_by_key) != len(reviews):
        raise ValueError("Each direction claim can have only one claim review")
    valid_keys = {
        (direction.id, claim.id)
        for direction in directions
        for claim in direction.claims
    }
    unknown_keys = set(review_by_key) - valid_keys
    if unknown_keys:
        direction_id, claim_id = min(unknown_keys)
        raise ValueError(
            f"Claim review references an unknown claim: {direction_id}/{claim_id}"
        )

    results: list[EvaluatedClaim] = []
    for direction in directions:
        for claim in direction.claims:
            review = review_by_key.get((direction.id, claim.id))
            if review is not None and set(claim.evidence_ids) & set(
                review.opposing_evidence_ids
            ):
                raise ValueError(
                    "The same evidence cannot support and oppose one claim"
                )
            support = evidence_strength(claim.evidence_ids, evidence_by_id)
            opposition = (
                evidence_strength(review.opposing_evidence_ids, evidence_by_id)
                if review is not None
                else None
            )
            results.append(
                EvaluatedClaim(
                    direction_id=direction.id,
                    claim_id=claim.id,
                    statement=claim.statement,
                    is_core=claim.is_core,
                    supporting_evidence_ids=claim.evidence_ids,
                    opposing_evidence_ids=(
                        review.opposing_evidence_ids if review is not None else []
                    ),
                    support_strength=support,
                    counterevidence_strength=opposition,
                    poc_testability=(
                        review.poc_testability if review is not None else None
                    ),
                    verdict=classify_claim_verdict(
                        support_strength=support,
                        counterevidence_strength=opposition,
                        strong_counterevidence=strong_counterevidence,
                    ),
                    rationale=(
                        review.rationale
                        if review is not None
                        else "Independent claim review is still missing."
                    ),
                )
            )
    return results


def _is_poc_viable(
    assessments: Sequence[EvaluatedClaim],
    *,
    minimum_claim_support: float,
    minimum_poc_testability: float,
) -> bool:
    core = [assessment for assessment in assessments if assessment.is_core]
    if not core or any(assessment.verdict == "refuted" for assessment in core):
        return False

    has_testable_supported_hypothesis = any(
        assessment.support_strength >= minimum_claim_support
        and assessment.poc_testability is not None
        and assessment.poc_testability >= minimum_poc_testability
        for assessment in core
    )
    unresolved_are_testable = all(
        assessment.verdict == "supported"
        or (
            assessment.poc_testability is not None
            and assessment.poc_testability >= minimum_poc_testability
        )
        for assessment in core
    )
    return has_testable_supported_hypothesis and unresolved_are_testable


def _research_or_no_viable(
    *,
    research_exhausted: bool,
    request: TargetedResearchRequest,
    reason: str,
    claim_assessments: Sequence[EvaluatedClaim] = (),
) -> PhaseCHandoff:
    if research_exhausted:
        return PhaseCHandoff(
            status="no_viable_direction",
            claim_assessments=list(claim_assessments),
            reason=(
                f"{reason} Added evidence remained insufficient after the "
                "bounded targeted-research budget was exhausted."
            ),
        )
    return PhaseCHandoff(
        status="research_required",
        claim_assessments=list(claim_assessments),
        research_request=request,
        reason=reason,
    )


def _poc_candidate(
    *,
    direction: RankedDirection,
    critique: CriticOutcome,
    assessments: list[EvaluatedClaim],
) -> PocCandidate:
    evidence_ids = list(
        dict.fromkeys(
            evidence_id
            for claim in direction.claims
            for evidence_id in claim.evidence_ids
        )
    )
    unresolved_questions = [
        item.question.question
        for item in critique.accepted_questions
        if item.question.direction_id == direction.id
    ]
    return PocCandidate(
        direction_id=direction.id,
        title=direction.title,
        hypothesis=direction.summary,
        evidence_ids=evidence_ids,
        evidence_coverage=direction.evidence_coverage,
        claim_assessments=assessments,
        unresolved_questions=unresolved_questions,
    )


def _claim_research_request(
    *,
    mission_goal: str,
    directions: Sequence[RankedDirection],
    assessments: Sequence[EvaluatedClaim],
    minimum_claim_support: float,
    minimum_poc_testability: float,
) -> TargetedResearchRequest:
    direction_by_id = {direction.id: direction for direction in directions}
    targets = [
        assessment
        for assessment in assessments
        if assessment.is_core
        and (
            assessment.support_strength < minimum_claim_support
            or assessment.counterevidence_strength is None
            or assessment.poc_testability is None
            or assessment.poc_testability < minimum_poc_testability
            or assessment.verdict == "refuted"
        )
    ][:3]
    queries = [
        (
            f"{mission_goal.strip()} "
            f"{direction_by_id[target.direction_id].title} {target.statement}"
        )
        for target in targets
    ]
    if not queries:
        queries = [mission_goal.strip()]
    return TargetedResearchRequest(
        queries=queries,
        direction_ids=list(dict.fromkeys(target.direction_id for target in targets)),
        claim_ids=list(dict.fromkeys(target.claim_id for target in targets)),
        reason=(
            "Retrieve support and counterevidence for core claims that remain "
            "unsupported, unreviewed, refuted, or not testable in a PoC."
        ),
    )
