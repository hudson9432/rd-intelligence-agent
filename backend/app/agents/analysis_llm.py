"""Adapter from B's LLMClient to Phase C provider protocols."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from app.core.llm import LLMClient, LLMStructuredOutputError
from app.prompts.analyst import build_analyst_messages
from app.prompts.critic import (
    build_claim_review_messages,
    build_critic_messages,
    build_question_review_messages,
)
from app.schemas.analysis import (
    AnalystOutcome,
    ClaimReview,
    CriticOutcome,
    CritiqueQuestionDraft,
    DirectionClaim,
    DirectionDraft,
    RankedDirection,
    SemanticQuestionScores,
)
from app.schemas.evidence_card import EvidenceCard


class AnalysisGenerationError(RuntimeError):
    """Raised when a real provider violates a Phase C structured contract."""


MAX_LLM_EVIDENCE_CARDS = 50


class _DirectionBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    directions: list[DirectionDraft] = Field(min_length=1, max_length=12)


class _QuestionBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    questions: list[CritiqueQuestionDraft] = Field(min_length=1, max_length=24)


class _ClaimReviewBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviews: list[ClaimReview] = Field(min_length=1)


class LLMAnalysisAdapter:
    """One adapter implementing all B-backed generation boundaries for C."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    def generate_directions(
        self, *, mission_goal: str, evidence: Sequence[EvidenceCard]
    ) -> Sequence[DirectionDraft]:
        bounded_evidence = list(evidence)[:MAX_LLM_EVIDENCE_CARDS]
        try:
            return self._llm_client.complete_structured(
                build_analyst_messages(
                    mission_goal=mission_goal,
                    evidence=bounded_evidence,
                ),
                _DirectionBatch,
                mock_factory=lambda: _DirectionBatch(
                    directions=_mock_directions(bounded_evidence)
                ),
            ).directions
        except LLMStructuredOutputError as error:
            raise AnalysisGenerationError(
                "LLM response did not match the direction-generation contract"
            ) from error

    def generate_questions(
        self,
        *,
        mission_goal: str,
        directions: Sequence[RankedDirection],
        evidence: Sequence[EvidenceCard],
    ) -> Sequence[CritiqueQuestionDraft]:
        bounded_evidence = list(evidence)[:MAX_LLM_EVIDENCE_CARDS]
        try:
            return self._llm_client.complete_structured(
                build_critic_messages(
                    mission_goal=mission_goal,
                    directions=directions,
                    evidence=bounded_evidence,
                ),
                _QuestionBatch,
                mock_factory=lambda: _QuestionBatch(
                    questions=_mock_questions(directions, bounded_evidence)
                ),
            ).questions
        except LLMStructuredOutputError as error:
            raise AnalysisGenerationError(
                "LLM response did not match the critique-question contract"
            ) from error

    def review_question(
        self,
        *,
        question: CritiqueQuestionDraft,
        direction: RankedDirection,
        evidence: Sequence[EvidenceCard],
    ) -> SemanticQuestionScores:
        bounded_evidence = list(evidence)[:MAX_LLM_EVIDENCE_CARDS]
        try:
            return self._llm_client.complete_structured(
                build_question_review_messages(
                    question=question,
                    direction=direction,
                    evidence=bounded_evidence,
                ),
                SemanticQuestionScores,
                mock_factory=lambda: SemanticQuestionScores(
                    rationality=0.85,
                    viewpoint_coverage=(
                        0.85
                        if question.evidence_ids or question.suggested_query
                        else 0.6
                    ),
                ),
            )
        except LLMStructuredOutputError as error:
            raise AnalysisGenerationError(
                "LLM response did not match the question-review contract"
            ) from error

    def review_claims(
        self,
        *,
        analysis: AnalystOutcome,
        critique: CriticOutcome,
        evidence: Sequence[EvidenceCard],
    ) -> Sequence[ClaimReview]:
        bounded_evidence = list(evidence)[:MAX_LLM_EVIDENCE_CARDS]
        try:
            return self._llm_client.complete_structured(
                build_claim_review_messages(
                    analysis=analysis,
                    critique=critique,
                    evidence=bounded_evidence,
                ),
                _ClaimReviewBatch,
                mock_factory=lambda: _ClaimReviewBatch(
                    reviews=[
                        ClaimReview(
                            direction_id=direction.id,
                            claim_id=claim.id,
                            opposing_evidence_ids=[],
                            poc_testability=0.8,
                            rationale=(
                                "Deterministic mock review marks the stated "
                                "hypothesis as measurable; it asserts no opposing "
                                "evidence."
                            ),
                        )
                        for direction in analysis.active_directions
                        for claim in direction.claims
                    ]
                ),
            ).reviews
        except LLMStructuredOutputError as error:
            raise AnalysisGenerationError(
                "LLM response did not match the claim-review contract"
            ) from error


def _mock_directions(evidence: Sequence[EvidenceCard]) -> list[DirectionDraft]:
    """Derive one direction per evidence card, deterministically.

    Ordering and identifiers come from evidence *content*, never from
    `EvidenceCard.id`. Those ids are assigned by persistence and differ on
    every run, so keying on them made the mock non-deterministic: the Analyst
    breaks coverage ties on direction title and id, so which directions became
    active — and therefore whether the run reached a PoC candidate — varied
    between identical runs. Invariant 7 requires demo and test modes to be
    deterministic.

    Evidence ids are still cited verbatim in the claims; provenance is
    unaffected.
    """

    drafted: list[tuple[str, str, EvidenceCard]] = []
    for card in evidence:
        statement = next(
            (
                value
                for value in (
                    card.result,
                    card.method,
                    card.problem,
                    *card.evidence_snippets_json,
                )
                if value
            ),
            None,
        )
        if statement is None:
            continue
        title = next(
            (
                value
                for value in (
                    *card.technology_tags_json,
                    card.method,
                    card.problem,
                )
                if value
            ),
            statement,
        )
        drafted.append((statement, title[:300], card))

    drafted.sort(key=lambda item: (item[1].casefold(), item[0]))

    directions: list[DirectionDraft] = []
    for position, (statement, title, card) in enumerate(drafted):
        # The position keeps ids unique when two cards state the same thing,
        # and the sort above makes the position itself content-determined.
        key = _stable_id("", str(position), title, statement)
        directions.append(
            DirectionDraft(
                id=f"direction{key}",
                title=title,
                summary=statement,
                claims=[
                    DirectionClaim(
                        id=f"claim{key}",
                        statement=statement,
                        evidence_ids=[card.id],
                    )
                ],
            )
        )
    return directions[:12]


def _mock_questions(
    directions: Sequence[RankedDirection],
    evidence: Sequence[EvidenceCard],
) -> list[CritiqueQuestionDraft]:
    evidence_by_id = {card.id: card for card in evidence}
    questions: list[CritiqueQuestionDraft] = []
    for direction in directions:
        for claim in direction.claims:
            limitations = [
                (evidence_id, evidence_by_id[evidence_id].limitation)
                for evidence_id in claim.evidence_ids
                if evidence_id in evidence_by_id
                and evidence_by_id[evidence_id].limitation
            ]
            if limitations:
                evidence_id, limitation = limitations[0]
                questions.append(
                    CritiqueQuestionDraft(
                        id=_stable_id("question", direction.id, claim.id),
                        direction_id=direction.id,
                        challenged_claim_id=claim.id,
                        question=(
                            "Does the documented limitation change the claim: "
                            f"{claim.statement}?"
                        ),
                        rationale=limitation,
                        evidence_ids=[evidence_id],
                    )
                )
            else:
                questions.append(
                    CritiqueQuestionDraft(
                        id=_stable_id("question", direction.id, claim.id),
                        direction_id=direction.id,
                        challenged_claim_id=claim.id,
                        question=f"What experiment would verify: {claim.statement}?",
                        rationale=(
                            "The supplied evidence states the claim but does not "
                            "record a limitation that tests its boundary."
                        ),
                        suggested_query=(
                            f"{direction.title} {claim.statement} experiment benchmark"
                        ),
                    )
                )
    return questions[:24]


def _stable_id(prefix: str, *values: str) -> str:
    digest = hashlib.sha256("\n".join(values).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"
