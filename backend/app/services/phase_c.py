"""Final Phase C gate between analysis/critique and D's orchestration."""

from __future__ import annotations

from app.schemas.analysis import (
    AnalystOutcome,
    CriticOutcome,
    PhaseCHandoff,
    PocCandidate,
    RankedDirection,
    TargetedResearchRequest,
)


def build_phase_c_handoff(
    *,
    mission_goal: str,
    analysis: AnalystOutcome,
    critique: CriticOutcome,
    research_exhausted: bool = False,
    minimum_direction_coverage: float = 0.6,
) -> PhaseCHandoff:
    """Return a PoC candidate, a bounded research request, or no viable result.

    D owns the iteration limit and marks research exhausted when it cannot
    execute another targeted research round. Phase C remains conservative: an
    unresolved research request cannot become a PoC merely because the loop
    budget ended.
    """

    if not mission_goal.strip():
        raise ValueError("mission_goal cannot be empty")
    if not 0 <= minimum_direction_coverage <= 1:
        raise ValueError("minimum_direction_coverage must be between zero and one")

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

    eligible = [
        direction
        for direction in analysis.active_directions
        if direction.evidence_coverage >= minimum_direction_coverage
    ]
    if not eligible:
        return _research_or_no_viable(
            research_exhausted=research_exhausted,
            request=TargetedResearchRequest(
                queries=_direction_queries(
                    mission_goal=mission_goal,
                    directions=analysis.active_directions,
                ),
                direction_ids=[
                    direction.id for direction in analysis.active_directions[:3]
                ],
                reason="No direction meets the minimum evidence-coverage threshold.",
            ),
            reason="No direction meets the minimum evidence-coverage threshold.",
        )

    return PhaseCHandoff(
        status="ready_for_poc",
        poc_candidates=[
            _poc_candidate(direction=direction, critique=critique)
            for direction in eligible
        ],
        reason=(
            "At least one direction has sufficient evidence coverage and no "
            "unresolved targeted-research request."
        ),
    )


def _research_or_no_viable(
    *,
    research_exhausted: bool,
    request: TargetedResearchRequest,
    reason: str,
) -> PhaseCHandoff:
    if research_exhausted:
        return PhaseCHandoff(
            status="no_viable_direction",
            reason=f"{reason} The targeted research budget is exhausted.",
        )
    return PhaseCHandoff(
        status="research_required",
        research_request=request,
        reason=reason,
    )


def _poc_candidate(
    *, direction: RankedDirection, critique: CriticOutcome
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
        unresolved_questions=unresolved_questions,
    )


def _direction_queries(
    *, mission_goal: str, directions: list[RankedDirection]
) -> list[str]:
    queries = [
        f"{mission_goal.strip()} {direction.title}"
        for direction in directions[:3]
    ]
    return queries or [mission_goal.strip()]
