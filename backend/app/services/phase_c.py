"""Final Phase C gate between analysis/critique and D's orchestration."""

from __future__ import annotations

import logging
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
from app.services.scoring import (
    UnknownEvidenceReferenceError,
    evidence_index,
    evidence_strength,
    validate_evidence_references,
)

logger = logging.getLogger(__name__)


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

    if critique.status == "research_required" and not research_exhausted:
        assert critique.research_request is not None
        return PhaseCHandoff(
            status="research_required",
            research_request=critique.research_request,
            reason="Material critique questions still require evidence.",
        )

    # Once the budget is spent, outstanding critique questions no longer decide
    # the outcome. A critic always has another question; that is not the same
    # as no direction being viable, and this contract reserves
    # `no_viable_direction` for "the research budget is exhausted *and* no
    # direction satisfies the core-claim viability rules". Short-circuiting
    # here skipped the second half of that test entirely, so claim evaluation
    # never ran on a real provider: a live critic attaches a suggested search
    # to almost every accepted question, which pinned the critique at
    # `research_required` no matter how much evidence had been gathered.
    # Falling through lets the evidence decide.

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
    review_by_key = _usable_reviews(
        directions=directions, evidence_by_id=evidence_by_id, reviews=reviews
    )

    results: list[EvaluatedClaim] = []
    for direction in directions:
        for claim in direction.claims:
            review = review_by_key.get((direction.id, claim.id))
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


def _usable_reviews(
    *,
    directions: Sequence[RankedDirection],
    evidence_by_id: dict[UUID, EvidenceCard],
    reviews: Sequence[ClaimReview],
) -> dict[tuple[str, str], ClaimReview]:
    """Keep only the reviews that can actually be applied to a claim.

    An independent reviewer is a model, and a model can contradict itself or
    cite evidence that does not exist. A review that cannot be applied is
    dropped and the claim is judged as if no review arrived, which the Phase C
    contract already defines: missing review stays `unknown` and is never
    converted into negative evidence. Discarding one bad review is therefore
    strictly safer than discarding the whole gate, which is what raising here
    used to do — it failed the entire mission after the evidence was gathered.
    """

    claim_support = {
        (direction.id, claim.id): set(claim.evidence_ids)
        for direction in directions
        for claim in direction.claims
    }

    usable: dict[tuple[str, str], ClaimReview] = {}
    for review in reviews:
        key = (review.direction_id, review.claim_id)
        reason: str | None = None

        if key not in claim_support:
            reason = "it reviews a claim that is not under analysis"
        elif key in usable:
            # The reviewer contradicted itself; neither copy can be trusted
            # over the other, so keep the first and drop the rest.
            reason = "a review for this claim was already supplied"
        elif claim_support[key] & set(review.opposing_evidence_ids):
            reason = "it cites the same evidence as both support and opposition"
        else:
            try:
                validate_evidence_references(
                    review.opposing_evidence_ids, evidence_by_id
                )
            except UnknownEvidenceReferenceError:
                reason = "it cites opposing evidence outside the supplied set"

        if reason is not None:
            logger.warning("Discarded claim review %s/%s: %s", key[0], key[1], reason)
            continue
        usable[key] = review
    return usable


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
        for item in [
            *critique.accepted_questions,
            *critique.research_gap_questions,
        ]
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
