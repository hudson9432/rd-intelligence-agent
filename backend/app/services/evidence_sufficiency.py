"""Deterministic evidence-pool sufficiency gate for Phase C."""

from __future__ import annotations

from collections.abc import Sequence

from app.schemas.analysis import (
    EvidenceEligibility,
    EvidenceSufficiencyReport,
    TargetedResearchRequest,
)
from app.schemas.evidence_card import EvidenceCard


def assess_evidence_sufficiency(
    evidence: Sequence[EvidenceCard],
    *,
    minimum_effective_evidence: int = 2,
    minimum_independent_sources: int = 2,
    minimum_relevance: float = 0.2,
    minimum_challenge_relevance: float = 0.1,
    minimum_extraction_confidence: float = 0.6,
) -> EvidenceSufficiencyReport:
    """Decide whether the evidence pool is substantial enough for analysis.

    Counts alone are not sufficient. A card is effective only when both its
    relevance and extraction confidence clear explicit thresholds, and
    corroboration is measured with distinct source IDs. Cards below the support
    relevance threshold may still enter the challenge pool when their
    extraction is reliable, they retain some mission relevance, and they state
    a result or limitation. Such cards can challenge a claim but cannot create
    or strengthen one. Result and limitation counts are reported for inspection
    but are not universal hard gates: a strategy article can be useful evidence
    without containing a benchmark.
    """

    if minimum_effective_evidence < 1:
        raise ValueError("minimum_effective_evidence must be positive")
    if minimum_independent_sources < 1:
        raise ValueError("minimum_independent_sources must be positive")
    if not 0 <= minimum_relevance <= 1:
        raise ValueError("minimum_relevance must be between zero and one")
    if not 0 <= minimum_challenge_relevance <= minimum_relevance:
        raise ValueError(
            "minimum_challenge_relevance must be between zero and minimum_relevance"
        )
    if not 0 <= minimum_extraction_confidence <= 1:
        raise ValueError("minimum_extraction_confidence must be between zero and one")

    assessments: list[EvidenceEligibility] = []
    effective_cards: list[EvidenceCard] = []
    for card in evidence:
        reasons = []
        if card.relevance_score < minimum_relevance:
            reasons.append("low_relevance")
        if card.extraction_confidence < minimum_extraction_confidence:
            reasons.append("low_extraction_confidence")
        eligible = not reasons
        challenge_eligible = eligible or (
            card.extraction_confidence >= minimum_extraction_confidence
            and card.relevance_score >= minimum_challenge_relevance
            and bool(card.result or card.limitation)
        )
        assessments.append(
            EvidenceEligibility(
                evidence_id=card.id,
                quality_score=round(
                    card.relevance_score * card.extraction_confidence, 4
                ),
                eligible=eligible,
                challenge_eligible=challenge_eligible,
                exclusion_reasons=reasons,
            )
        )
        if eligible:
            effective_cards.append(card)

    independent_source_count = len({card.source_id for card in effective_cards})
    missing_requirements: list[str] = []
    if len(effective_cards) < minimum_effective_evidence:
        missing_requirements.append("effective_evidence")
    if independent_source_count < minimum_independent_sources:
        missing_requirements.append("independent_sources")

    return EvidenceSufficiencyReport(
        sufficient=not missing_requirements,
        total_evidence_count=len(evidence),
        effective_evidence_count=len(effective_cards),
        challenge_evidence_count=sum(
            assessment.challenge_eligible for assessment in assessments
        ),
        independent_source_count=independent_source_count,
        result_bearing_count=sum(bool(card.result) for card in effective_cards),
        limitation_bearing_count=sum(bool(card.limitation) for card in effective_cards),
        minimum_effective_evidence=minimum_effective_evidence,
        minimum_independent_sources=minimum_independent_sources,
        minimum_relevance=minimum_relevance,
        minimum_challenge_relevance=minimum_challenge_relevance,
        minimum_extraction_confidence=minimum_extraction_confidence,
        assessments=assessments,
        missing_requirements=missing_requirements,
    )


def partition_evidence_by_access(
    evidence: Sequence[EvidenceCard], report: EvidenceSufficiencyReport
) -> tuple[list[EvidenceCard], list[EvidenceCard]]:
    """Return support and challenge pools from an audited sufficiency report.

    The challenge pool is a superset of the support pool. Unknown or duplicate
    evidence IDs are rejected because silently assigning permissions would make
    the audit record disagree with the data shown to an agent.
    """

    assessment_by_id = {
        assessment.evidence_id: assessment for assessment in report.assessments
    }
    if len(assessment_by_id) != len(report.assessments):
        raise ValueError("Evidence sufficiency report contains duplicate IDs")

    support_pool: list[EvidenceCard] = []
    challenge_pool: list[EvidenceCard] = []
    seen: set[object] = set()
    for card in evidence:
        if card.id in seen:
            raise ValueError("Evidence pool contains duplicate IDs")
        seen.add(card.id)
        assessment = assessment_by_id.get(card.id)
        if assessment is None:
            raise ValueError("Evidence is missing from its sufficiency report")
        if assessment.eligible:
            support_pool.append(card)
        if assessment.challenge_eligible:
            challenge_pool.append(card)

    if len(seen) != len(assessment_by_id):
        raise ValueError("Sufficiency report references evidence outside the pool")
    return support_pool, challenge_pool


def build_sufficiency_research_request(
    *, mission_goal: str, report: EvidenceSufficiencyReport
) -> TargetedResearchRequest:
    """Turn unmet deterministic requirements into bounded search queries."""

    goal = " ".join(mission_goal.split())
    queries: list[str] = []
    if "effective_evidence" in report.missing_requirements:
        queries.append(f"{goal} empirical benchmark independent study")
    if "independent_sources" in report.missing_requirements:
        queries.append(f"{goal} independent replication external evaluation")
    if not queries:
        queries = [goal]

    return TargetedResearchRequest(
        queries=list(dict.fromkeys(queries))[:3],
        reason=(
            "The Phase C evidence pool does not meet the minimum effective-"
            "evidence and independent-source requirements."
        ),
    )
