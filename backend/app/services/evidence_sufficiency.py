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
    minimum_extraction_confidence: float = 0.6,
) -> EvidenceSufficiencyReport:
    """Decide whether the evidence pool is substantial enough for analysis.

    Counts alone are not sufficient. A card is effective only when both its
    relevance and extraction confidence clear explicit thresholds, and
    corroboration is measured with distinct source IDs. Result and limitation
    counts are reported for inspection but are not universal hard gates: a
    strategy article can be useful evidence without containing a benchmark.
    """

    if minimum_effective_evidence < 1:
        raise ValueError("minimum_effective_evidence must be positive")
    if minimum_independent_sources < 1:
        raise ValueError("minimum_independent_sources must be positive")
    if not 0 <= minimum_relevance <= 1:
        raise ValueError("minimum_relevance must be between zero and one")
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
        assessments.append(
            EvidenceEligibility(
                evidence_id=card.id,
                quality_score=round(
                    card.relevance_score * card.extraction_confidence, 4
                ),
                eligible=eligible,
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
        independent_source_count=independent_source_count,
        result_bearing_count=sum(bool(card.result) for card in effective_cards),
        limitation_bearing_count=sum(bool(card.limitation) for card in effective_cards),
        minimum_effective_evidence=minimum_effective_evidence,
        minimum_independent_sources=minimum_independent_sources,
        minimum_relevance=minimum_relevance,
        minimum_extraction_confidence=minimum_extraction_confidence,
        assessments=assessments,
        missing_requirements=missing_requirements,
    )


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
