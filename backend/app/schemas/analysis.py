"""Typed contracts for opportunity analysis and adversarial critique.

These contracts are intentionally isolated from the persistence schemas. They
allow Phase C to progress against mock providers without changes to shared
database or API contracts.
"""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

UnitScore = Annotated[float, Field(ge=0, le=1)]
QuestionRejectionReason = Literal[
    "low_diversity", "low_rationality", "low_viewpoint_coverage"
]
EvidenceExclusionReason = Literal["low_relevance", "low_extraction_confidence"]


class DirectionClaim(BaseModel):
    """One testable statement made in support of a proposed direction."""

    id: str = Field(min_length=1, max_length=100)
    statement: str = Field(min_length=1)
    evidence_ids: list[UUID] = Field(default_factory=list)
    is_core: bool = True


class DirectionDraft(BaseModel):
    """A provider-generated direction before deterministic ranking."""

    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1)
    claims: list[DirectionClaim] = Field(min_length=1)


class RankedDirection(DirectionDraft):
    """A direction enriched with deterministic evidence coverage."""

    evidence_coverage: UnitScore
    rank: int = Field(ge=1)


class AnalystOutcome(BaseModel):
    """Up to four active directions, with every alternative retained."""

    status: Literal["ready", "research_required"]
    active_directions: list[RankedDirection] = Field(default_factory=list, max_length=4)
    candidate_directions: list[RankedDirection] = Field(default_factory=list)
    reason: str | None = None

    @model_validator(mode="after")
    def validate_status(self) -> "AnalystOutcome":
        if self.status == "ready" and not self.active_directions:
            raise ValueError("A ready analysis must contain at least one direction")
        if self.status == "research_required" and self.active_directions:
            raise ValueError("A research-required analysis cannot select directions")
        return self


class CritiqueQuestionDraft(BaseModel):
    """A challenge generated for a claim or an uncovered evidence gap."""

    id: str = Field(min_length=1, max_length=100)
    direction_id: str = Field(min_length=1, max_length=100)
    challenged_claim_id: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    evidence_ids: list[UUID] = Field(default_factory=list)
    suggested_query: str | None = Field(default=None, min_length=1)


class SemanticQuestionScores(BaseModel):
    """Scores supplied by an independent semantic question reviewer."""

    rationality: UnitScore
    viewpoint_coverage: UnitScore


class QuestionScores(SemanticQuestionScores):
    """Complete scores after deterministic diversity evaluation."""

    diversity: UnitScore


class EvaluatedCritiqueQuestion(BaseModel):
    """A critique question with its review result and rejection reasons."""

    question: CritiqueQuestionDraft
    scores: QuestionScores
    rejection_reasons: list[QuestionRejectionReason] = Field(default_factory=list)


class TargetedResearchRequest(BaseModel):
    """Bounded re-search request produced at the end of Phase C."""

    queries: list[str] = Field(min_length=1, max_length=3)
    direction_ids: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=1)


class EvidenceEligibility(BaseModel):
    """How one evidence card may be used by Phase C.

    ``eligible`` is deliberately the stricter support permission. A card may
    fail that gate while remaining ``challenge_eligible`` when it is reliable
    enough to expose a limitation or conflicting result. This asymmetry keeps
    weak evidence from increasing a direction's score without hiding useful
    counterevidence from the Critic.
    """

    evidence_id: UUID
    quality_score: UnitScore
    eligible: bool
    challenge_eligible: bool
    exclusion_reasons: list[EvidenceExclusionReason] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_eligibility(self) -> "EvidenceEligibility":
        if self.eligible and self.exclusion_reasons:
            raise ValueError("Eligible evidence cannot have exclusion reasons")
        if not self.eligible and not self.exclusion_reasons:
            raise ValueError("Excluded evidence needs at least one reason")
        if self.eligible and not self.challenge_eligible:
            raise ValueError("Support-eligible evidence must enter the challenge pool")
        return self


class EvidenceSufficiencyReport(BaseModel):
    """Deterministic entry gate and audit record for Phase C."""

    sufficient: bool
    total_evidence_count: int = Field(ge=0)
    effective_evidence_count: int = Field(ge=0)
    challenge_evidence_count: int = Field(ge=0)
    independent_source_count: int = Field(ge=0)
    result_bearing_count: int = Field(ge=0)
    limitation_bearing_count: int = Field(ge=0)
    minimum_effective_evidence: int = Field(ge=1)
    minimum_independent_sources: int = Field(ge=1)
    minimum_relevance: UnitScore
    minimum_challenge_relevance: UnitScore
    minimum_extraction_confidence: UnitScore
    assessments: list[EvidenceEligibility] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)


class CriticOutcome(BaseModel):
    """Critique questions that survive review plus the re-search signal."""

    status: Literal["ready", "research_required"]
    accepted_questions: list[EvaluatedCritiqueQuestion] = Field(default_factory=list)
    research_gap_questions: list[EvaluatedCritiqueQuestion] = Field(
        default_factory=list
    )
    rejected_questions: list[EvaluatedCritiqueQuestion] = Field(default_factory=list)
    suggested_queries: list[str] = Field(default_factory=list)
    research_request: TargetedResearchRequest | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def validate_status(self) -> "CriticOutcome":
        if self.status == "ready" and not self.accepted_questions:
            raise ValueError("A ready critique must contain an accepted question")
        if self.status == "ready" and self.research_request is not None:
            raise ValueError("A ready critique cannot contain a research request")
        if self.status == "research_required" and self.research_request is None:
            raise ValueError("A research-required critique needs a research request")
        return self


ClaimVerdict = Literal["supported", "contested", "unknown", "refuted"]
ClaimResolutionStatus = Literal["resolved", "poc_testable", "research_gap", "fatal"]


class ClaimReview(BaseModel):
    """Independent review input used to judge one direction claim."""

    direction_id: str = Field(min_length=1, max_length=100)
    claim_id: str = Field(min_length=1, max_length=100)
    opposing_evidence_ids: list[UUID] = Field(default_factory=list)
    poc_testability: UnitScore
    rationale: str = Field(min_length=1)


class EvaluatedClaim(BaseModel):
    """Deterministic pro/con result for one claim."""

    direction_id: str = Field(min_length=1, max_length=100)
    claim_id: str = Field(min_length=1, max_length=100)
    statement: str = Field(min_length=1)
    is_core: bool
    supporting_evidence_ids: list[UUID] = Field(default_factory=list)
    opposing_evidence_ids: list[UUID] = Field(default_factory=list)
    support_strength: UnitScore
    counterevidence_strength: UnitScore | None = None
    poc_testability: UnitScore | None = None
    verdict: ClaimVerdict
    resolution_status: ClaimResolutionStatus
    rationale: str = Field(min_length=1)


class PocCandidate(BaseModel):
    """Evidence-grounded direction that D can turn into an executable PoC."""

    direction_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    hypothesis: str = Field(min_length=1)
    evidence_ids: list[UUID] = Field(min_length=1)
    evidence_coverage: UnitScore
    claim_assessments: list[EvaluatedClaim] = Field(min_length=1)
    unresolved_questions: list[str] = Field(default_factory=list)


class PhaseCHandoff(BaseModel):
    """The only three outcomes Phase C can hand to orchestration."""

    status: Literal["ready_for_poc", "research_required", "no_viable_direction"]
    poc_candidates: list[PocCandidate] = Field(default_factory=list, max_length=4)
    claim_assessments: list[EvaluatedClaim] = Field(default_factory=list)
    research_request: TargetedResearchRequest | None = None
    evidence_sufficiency: EvidenceSufficiencyReport | None = None
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_handoff(self) -> "PhaseCHandoff":
        if self.status == "ready_for_poc" and not self.poc_candidates:
            raise ValueError("A PoC-ready handoff needs at least one candidate")
        if self.status != "ready_for_poc" and self.poc_candidates:
            raise ValueError("Only a PoC-ready handoff can contain PoC candidates")
        if self.status == "research_required" and self.research_request is None:
            raise ValueError("A research-required handoff needs a research request")
        if self.status != "research_required" and self.research_request is not None:
            raise ValueError("Only a research-required handoff can request research")
        return self
