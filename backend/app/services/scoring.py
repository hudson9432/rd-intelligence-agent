"""Deterministic scoring rules shared by Phase C agents."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from uuid import UUID

from app.schemas.analysis import DirectionDraft
from app.schemas.evidence_card import EvidenceCard

_NON_WORD = re.compile(r"[^\w\u3400-\u9fff]+", re.UNICODE)


class UnknownEvidenceReferenceError(ValueError):
    """Raised when generated analysis cites evidence outside the supplied set."""


def evidence_index(evidence: Sequence[EvidenceCard]) -> dict[UUID, EvidenceCard]:
    """Build an index while rejecting evidence mixed across missions."""

    mission_ids = {card.mission_id for card in evidence}
    if len(mission_ids) > 1:
        raise ValueError("Analysis evidence must belong to one mission")
    return {card.id: card for card in evidence}


def validate_evidence_references(
    evidence_ids: Iterable[UUID], evidence_by_id: dict[UUID, EvidenceCard]
) -> None:
    """Reject unknown evidence IDs instead of silently losing provenance."""

    unknown = sorted(
        (
            evidence_id
            for evidence_id in set(evidence_ids)
            if evidence_id not in evidence_by_id
        ),
        key=str,
    )
    if unknown:
        joined = ", ".join(str(evidence_id) for evidence_id in unknown)
        raise UnknownEvidenceReferenceError(f"Unknown evidence IDs: {joined}")


def direction_evidence_coverage(
    direction: DirectionDraft, evidence_by_id: dict[UUID, EvidenceCard]
) -> float:
    """Measure how well cited evidence supports all claims in a direction.

    Unsupported claims receive zero rather than a negative score: absence of
    evidence is not evidence against a claim.
    """

    all_ids = [
        evidence_id
        for claim in direction.claims
        for evidence_id in claim.evidence_ids
    ]
    validate_evidence_references(all_ids, evidence_by_id)

    claim_scores: list[float] = []
    for claim in direction.claims:
        if not claim.evidence_ids:
            claim_scores.append(0.0)
            continue

        cards = [evidence_by_id[evidence_id] for evidence_id in claim.evidence_ids]
        qualities = [
            card.relevance_score * card.extraction_confidence for card in cards
        ]
        independent_sources = len({card.source_id for card in cards})
        corroboration_bonus = min(0.2, max(0, independent_sources - 1) * 0.1)
        claim_scores.append(min(1.0, max(qualities) + corroboration_bonus))

    return round(sum(claim_scores) / len(claim_scores), 4)


def question_diversity(question: str, accepted_questions: Sequence[str]) -> float:
    """Return one minus the greatest similarity to accepted questions."""

    if not accepted_questions:
        return 1.0

    candidate_tokens = _bigrams(question)
    greatest_similarity = max(
        _jaccard(candidate_tokens, _bigrams(existing))
        for existing in accepted_questions
    )
    return round(1.0 - greatest_similarity, 4)


def _bigrams(value: str) -> set[str]:
    normalized = _NON_WORD.sub("", value.casefold())
    if len(normalized) < 2:
        return {normalized} if normalized else set()
    return {normalized[index : index + 2] for index in range(len(normalized) - 1)}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    union = left | right
    return len(left & right) / len(union) if union else 0.0
