"""Decision Agent: scores each candidate and recommends one.

Phase C asks whether a direction *can* be settled by experiment. This asks
whether it is *worth* settling — a different question, on dimensions Phase C
never looks at. Nothing before this point checks whether a direction answers
the mission's question at all: the Analyst ranks by evidence coverage and
breaks ties on title, so a well-evidenced but tangential direction wins.

Four dimensions are rated by a model against supplied evidence; two are derived
in code from what Phase C established, and the combining formula is code as
well. `AGENTS.md` requires scoring and routing to stay deterministic, and a
0–100 number is exactly the kind of thing that reads as measurement, so the
model contributes judgement and never arithmetic.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.llm import LLMClient, LLMStructuredOutputError
from app.prompts.decision import build_decision_messages
from app.schemas.analysis import PhaseCHandoff, PocCandidate
from app.schemas.evidence_card import EvidenceCard
from app.schemas.technology_opportunity import TechnologyOpportunityCreate
from app.schemas.workflow import WorkflowDecision
from app.services.opportunity_scoring import (
    derive_evidence_strength,
    derive_poc_feasibility,
    overall_score,
)

Rating = Annotated[int, Field(ge=1, le=5)]


class DecisionScoringError(RuntimeError):
    """Raised when a provider cannot produce a usable set of ratings."""


class _CandidateRating(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal_alignment: Rating
    technical_maturity: Rating
    novelty: Rating
    implementation_difficulty: Rating
    rationale: str = Field(min_length=1)


class ScoredOpportunity(BaseModel):
    """One candidate with its score, ready to store and to compare."""

    model_config = ConfigDict(extra="forbid")

    candidate: PocCandidate
    opportunity: TechnologyOpportunityCreate


class DecisionAgent:
    """Scores every candidate, then recommends the highest scoring one."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    def score(
        self,
        *,
        mission_id: UUID,
        mission_goal: str,
        handoff: PhaseCHandoff,
        evidence: Sequence[EvidenceCard],
    ) -> list[ScoredOpportunity]:
        """Score each candidate, best first.

        Every candidate is scored rather than only the eventual winner: the
        point of a score is comparison, and a reader who cannot see why the
        others lost has no way to disagree with the recommendation.
        """

        scored = [
            ScoredOpportunity(
                candidate=candidate,
                opportunity=self._score_one(
                    mission_id=mission_id,
                    mission_goal=mission_goal,
                    candidate=candidate,
                    evidence=evidence,
                ),
            )
            for candidate in handoff.poc_candidates
        ]
        scored.sort(
            key=lambda item: (
                -item.opportunity.overall_score,
                item.candidate.direction_id,
            )
        )
        return scored

    def _score_one(
        self,
        *,
        mission_id: UUID,
        mission_goal: str,
        candidate: PocCandidate,
        evidence: Sequence[EvidenceCard],
    ) -> TechnologyOpportunityCreate:
        try:
            rating = self._llm_client.complete_structured(
                build_decision_messages(
                    mission_goal=mission_goal,
                    candidate=candidate,
                    evidence=evidence,
                ),
                _CandidateRating,
                mock_factory=lambda: _mock_rating(candidate),
            )
        except LLMStructuredOutputError as error:
            raise DecisionScoringError(
                "LLM response did not match the opportunity-rating contract"
            ) from error

        evidence_strength = derive_evidence_strength(candidate)
        poc_feasibility = derive_poc_feasibility(candidate)

        return TechnologyOpportunityCreate(
            mission_id=mission_id,
            name=candidate.title[:300],
            description=candidate.hypothesis,
            # Only ids the candidate cites, so the record stays traceable and
            # the repository's same-mission check can verify it.
            related_evidence_ids_json=list(candidate.evidence_ids),
            novelty=rating.novelty,
            technical_maturity=rating.technical_maturity,
            implementation_difficulty=rating.implementation_difficulty,
            goal_alignment=rating.goal_alignment,
            poc_feasibility=poc_feasibility,
            evidence_strength=evidence_strength,
            overall_score=overall_score(
                novelty=rating.novelty,
                goal_alignment=rating.goal_alignment,
                technical_maturity=rating.technical_maturity,
                poc_feasibility=poc_feasibility,
                evidence_strength=evidence_strength,
                implementation_difficulty=rating.implementation_difficulty,
            ),
            rationale=rating.rationale,
        )


def recommend(scored: Sequence[ScoredOpportunity]) -> WorkflowDecision:
    """Turn the ranking into the orchestrator's go or no-go.

    A score cannot decide on its own where the bar sits, and inventing a
    threshold would be a product decision dressed as arithmetic. Phase C has
    already ruled that every candidate here is testable, so the recommendation
    follows the ranking and the score explains the choice rather than gating it.
    """

    if not scored:
        return WorkflowDecision(
            recommendation="do_not_proceed",
            rationale="No candidate direction was available to score.",
        )

    best = scored[0]
    runners = ", ".join(
        f"{item.candidate.title[:40]} ({item.opportunity.overall_score})"
        for item in scored[1:]
    )
    rationale = (
        f"Highest scoring direction at {best.opportunity.overall_score} of 100: "
        f"{best.opportunity.rationale}"
    )
    if runners:
        rationale = f"{rationale} Ranked above: {runners}."

    return WorkflowDecision(
        recommendation="proceed_with_poc",
        rationale=rationale,
        selected_direction_id=best.candidate.direction_id,
    )


def _mock_rating(candidate: PocCandidate) -> _CandidateRating:
    """Offline ratings derived from the candidate, not guessed.

    Only two of the four have anything in the candidate to stand on, so the
    other two take the middle of the scale and say so. A mock that invented a
    spread would make the scoring look more informed offline than it is.
    """

    settled = sum(
        1
        for assessment in candidate.claim_assessments
        if assessment.verdict == "supported"
    )
    total = len(candidate.claim_assessments) or 1

    return _CandidateRating(
        # A direction whose claims are settled reads as more mature, and one
        # still full of open questions reads as less explored.
        technical_maturity=max(1, min(5, round(1 + 4 * settled / total))),
        novelty=max(1, min(5, 1 + len(candidate.unresolved_questions))),
        goal_alignment=3,
        implementation_difficulty=3,
        rationale=(
            "Deterministic offline rating. Maturity follows the share of "
            "settled claims and novelty follows the count of open questions; "
            "alignment and difficulty are held at the middle of the scale "
            "because the candidate carries nothing to judge them by."
        ),
    )
