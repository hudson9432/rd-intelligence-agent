"""Adversarial critique with independently scored candidate questions."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol
from uuid import UUID

from app.schemas.analysis import (
    AnalystOutcome,
    CriticOutcome,
    CritiqueQuestionDraft,
    EvaluatedCritiqueQuestion,
    QuestionRejectionReason,
    QuestionScores,
    RankedDirection,
    SemanticQuestionScores,
    TargetedResearchRequest,
)
from app.schemas.evidence_card import EvidenceCard
from app.services.scoring import (
    evidence_index,
    question_diversity,
    validate_evidence_references,
)


class CritiqueQuestionGenerator(Protocol):
    """Provider boundary for generating challenges and replacement candidates."""

    def generate_questions(
        self,
        *,
        mission_goal: str,
        directions: Sequence[RankedDirection],
        evidence: Sequence[EvidenceCard],
    ) -> Sequence[CritiqueQuestionDraft]: ...


class QuestionReviewer(Protocol):
    """Independent semantic reviewer, separate from the question generator."""

    def review_question(
        self,
        *,
        question: CritiqueQuestionDraft,
        direction: RankedDirection,
        evidence: Sequence[EvidenceCard],
    ) -> SemanticQuestionScores: ...


class CriticAgent:
    """Challenge selected directions and filter weak or repetitive questions."""

    def __init__(
        self,
        generator: CritiqueQuestionGenerator,
        reviewer: QuestionReviewer,
        *,
        minimum_score: float = 0.6,
        max_questions: int = 6,
        max_candidate_questions: int = 24,
    ) -> None:
        if not 0 <= minimum_score <= 1:
            raise ValueError("minimum_score must be between zero and one")
        if max_questions < 1:
            raise ValueError("max_questions must be positive")
        if max_candidate_questions < max_questions:
            raise ValueError(
                "max_candidate_questions cannot be smaller than max_questions"
            )
        self.generator = generator
        self.reviewer = reviewer
        self.minimum_score = minimum_score
        self.max_questions = max_questions
        self.max_candidate_questions = max_candidate_questions

    def critique(
        self,
        *,
        mission_goal: str,
        analysis: AnalystOutcome,
        evidence: Sequence[EvidenceCard],
    ) -> CriticOutcome:
        if not mission_goal.strip():
            raise ValueError("mission_goal cannot be empty")
        if analysis.status != "ready":
            return CriticOutcome(
                status="research_required",
                research_request=TargetedResearchRequest(
                    queries=[mission_goal.strip()],
                    reason="No evidence-backed direction is ready for critique.",
                ),
                reason="No evidence-backed direction is ready for critique.",
            )

        directions = {
            direction.id: direction for direction in analysis.active_directions
        }
        evidence_by_id = evidence_index(evidence)
        candidates = list(
            self.generator.generate_questions(
                mission_goal=mission_goal,
                directions=analysis.active_directions,
                evidence=evidence,
            )
        )[: self.max_candidate_questions]

        accepted: list[EvaluatedCritiqueQuestion] = []
        rejected: list[EvaluatedCritiqueQuestion] = []
        accepted_texts: list[str] = []
        seen_question_ids: set[str] = set()

        # Candidates are a replacement queue: a rejected question consumes no
        # accepted slot, so the next candidate is considered automatically.
        for candidate in candidates:
            if len(accepted) >= self.max_questions:
                break
            if candidate.id in seen_question_ids:
                continue
            seen_question_ids.add(candidate.id)

            direction = self._validate_question(
                candidate, directions, evidence_by_id
            )
            semantic = self.reviewer.review_question(
                question=candidate,
                direction=direction,
                evidence=evidence,
            )
            scores = QuestionScores(
                diversity=question_diversity(candidate.question, accepted_texts),
                rationality=semantic.rationality,
                viewpoint_coverage=semantic.viewpoint_coverage,
            )
            reasons: list[QuestionRejectionReason] = []
            if scores.diversity < self.minimum_score:
                reasons.append("low_diversity")
            if scores.rationality < self.minimum_score:
                reasons.append("low_rationality")
            if scores.viewpoint_coverage < self.minimum_score:
                reasons.append("low_viewpoint_coverage")

            evaluated = EvaluatedCritiqueQuestion(
                question=candidate,
                scores=scores,
                rejection_reasons=reasons,
            )
            if reasons:
                rejected.append(evaluated)
                continue

            accepted.append(evaluated)
            accepted_texts.append(candidate.question)

        if not accepted:
            research_request = _fallback_research_request(
                mission_goal=mission_goal,
                directions=analysis.active_directions,
            )
            return CriticOutcome(
                status="research_required",
                rejected_questions=rejected,
                suggested_queries=research_request.queries,
                research_request=research_request,
                reason=(
                    "Every candidate critique question failed review; more "
                    "evidence is required before a defensible challenge can be formed."
                ),
            )

        suggested_queries = _unique_queries(
            item.question.suggested_query for item in accepted
        )[:3]
        research_request = None
        status = "ready"
        if suggested_queries:
            status = "research_required"
            research_request = TargetedResearchRequest(
                queries=suggested_queries,
                direction_ids=_unique_values(
                    item.question.direction_id for item in accepted
                ),
                claim_ids=_unique_values(
                    item.question.challenged_claim_id for item in accepted
                ),
                reason="Accepted critique questions expose evidence gaps.",
            )

        return CriticOutcome(
            status=status,
            accepted_questions=accepted,
            rejected_questions=rejected,
            suggested_queries=suggested_queries,
            research_request=research_request,
        )

    @staticmethod
    def _validate_question(
        candidate: CritiqueQuestionDraft,
        directions: dict[str, RankedDirection],
        evidence_by_id: dict[UUID, EvidenceCard],
    ) -> RankedDirection:
        direction = directions.get(candidate.direction_id)
        if direction is None:
            raise ValueError(
                f"Question references inactive direction: {candidate.direction_id}"
            )
        claim_ids = {claim.id for claim in direction.claims}
        if candidate.challenged_claim_id not in claim_ids:
            raise ValueError(
                "Question must challenge a claim from its referenced direction"
            )
        validate_evidence_references(candidate.evidence_ids, evidence_by_id)
        return direction


def _unique_queries(queries: Iterable[str | None]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for query in queries:
        if query is None:
            continue
        normalized = " ".join(query.split())
        key = normalized.casefold()
        if normalized and key not in seen:
            seen.add(key)
            result.append(normalized)
    return result


def _unique_values(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _fallback_research_request(
    *, mission_goal: str, directions: Sequence[RankedDirection]
) -> TargetedResearchRequest:
    claim_targets = [
        (direction, claim)
        for direction in directions
        for claim in direction.claims
        if not claim.evidence_ids
    ]
    if not claim_targets:
        claim_targets = [
            (direction, claim)
            for direction in directions
            for claim in direction.claims
        ]
    claim_targets = claim_targets[:3]
    queries = [
        f"{mission_goal.strip()} {direction.title} {claim.statement}"
        for direction, claim in claim_targets
    ]
    if not queries:
        queries = [mission_goal.strip()]
    return TargetedResearchRequest(
        queries=queries,
        direction_ids=_unique_values(
            direction.id for direction, _claim in claim_targets
        ),
        claim_ids=_unique_values(claim.id for _direction, claim in claim_targets),
        reason=(
            "No critique question passed review; retrieve evidence for the least "
            "supported claims before critique is retried."
        ),
    )
