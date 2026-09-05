"""Aggregate mission result and audit-report contracts."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.action_plan import ActionPlan
from app.schemas.analysis import (
    ClaimVerdict,
    EvidenceEligibility,
    EvidenceSufficiencyReport,
    PhaseCHandoff,
)
from app.schemas.coverage_report import CoverageReport
from app.schemas.evidence_card import EvidenceCard
from app.schemas.research_mission import ResearchMissionDetail
from app.schemas.source_document import SourceDocument
from app.schemas.technology_opportunity import TechnologyOpportunity
from app.schemas.workflow import WorkflowDecision


class ClaimVerdictCounts(BaseModel):
    """Stable counters for every Phase C claim outcome."""

    supported: int = Field(default=0, ge=0)
    contested: int = Field(default=0, ge=0)
    unknown: int = Field(default=0, ge=0)
    refuted: int = Field(default=0, ge=0)


class AuditFinding(BaseModel):
    """One deterministic reason the generated result needs attention."""

    severity: Literal["warning", "blocker"]
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)


class MissionAuditReport(BaseModel):
    """Compact explanation of what evidence and claims drove the result."""

    status: Literal["pass", "needs_review", "insufficient"]
    phase_c_status: str
    phase_c_reason: str
    evidence_sufficiency: EvidenceSufficiencyReport | None = None
    accepted_evidence_ids: list[UUID] = Field(default_factory=list)
    excluded_evidence: list[EvidenceEligibility] = Field(default_factory=list)
    supporting_evidence_ids: list[UUID] = Field(default_factory=list)
    opposing_evidence_ids: list[UUID] = Field(default_factory=list)
    claim_verdict_counts: ClaimVerdictCounts = Field(default_factory=ClaimVerdictCounts)
    unresolved_questions: list[str] = Field(default_factory=list)
    highest_opportunity_score: float | None = Field(default=None, ge=0, le=100)
    findings: list[AuditFinding] = Field(default_factory=list)


class MissionResult(BaseModel):
    """One read model for a mission's evidence, decision, and PoC plan."""

    mission: ResearchMissionDetail
    sources: list[SourceDocument] = Field(default_factory=list)
    evidence: list[EvidenceCard] = Field(default_factory=list)
    handoff: PhaseCHandoff | None = None
    audit: MissionAuditReport | None = None
    opportunities: list[TechnologyOpportunity] = Field(default_factory=list)
    decision: WorkflowDecision | None = None
    coverage_report: CoverageReport | None = None
    action_plan: ActionPlan | None = None


def count_verdicts(verdicts: list[ClaimVerdict]) -> ClaimVerdictCounts:
    """Build explicit counters without accepting arbitrary dictionary keys."""

    counts = ClaimVerdictCounts()
    for verdict in verdicts:
        setattr(counts, verdict, getattr(counts, verdict) + 1)
    return counts
