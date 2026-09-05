"""Read-side aggregation for a complete, auditable mission result."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any, TypeVar
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models.agent_event import AgentEvent
from app.repositories.action_plan import ActionPlanRepository
from app.repositories.agent_event import AgentEventRepository
from app.repositories.coverage_report import CoverageReportRepository
from app.repositories.evidence_card import EvidenceCardRepository
from app.repositories.source_document import SourceDocumentRepository
from app.repositories.technology_opportunity import TechnologyOpportunityRepository
from app.schemas.analysis import PhaseCHandoff
from app.schemas.mission_result import (
    AuditFinding,
    ClaimVerdictCounts,
    MissionAuditReport,
    MissionResult,
    count_verdicts,
)
from app.schemas.research_mission import MissionStatus
from app.schemas.workflow import WorkflowDecision
from app.services.mission import MissionService

UniqueValue = TypeVar("UniqueValue")


class MissionResultService:
    """Assemble persisted workflow artifacts without bypassing repositories."""

    def __init__(self, session: Session) -> None:
        self._missions = MissionService(session)
        self._sources = SourceDocumentRepository(session)
        self._evidence = EvidenceCardRepository(session)
        self._opportunities = TechnologyOpportunityRepository(session)
        self._coverage = CoverageReportRepository(session)
        self._actions = ActionPlanRepository(session)
        self._events = AgentEventRepository(session)

    def get(self, mission_id: UUID | str) -> MissionResult:
        mission = self._missions.get(mission_id)
        events = self._events.list_for_mission(mission_id)
        completion = _latest_event(events, "workflow_completed")
        handoff_event = _latest_event(events, "handoff_produced")
        handoff = _parse_handoff(completion) or _parse_handoff(handoff_event)
        decision = _parse_decision(completion)
        opportunities = self._opportunities.list_for_mission(mission_id)

        action_plan = None
        if (
            mission.status == MissionStatus.COMPLETED
            and decision is not None
            and decision.recommendation == "proceed_with_poc"
        ):
            action_plan = self._actions.get_for_mission(mission_id)

        return MissionResult(
            mission=mission,
            sources=self._sources.list_for_mission(mission_id),
            evidence=self._evidence.list_for_mission(mission_id),
            handoff=handoff,
            audit=_build_audit(
                handoff,
                highest_opportunity_score=(
                    opportunities[0].overall_score if opportunities else None
                ),
            ),
            opportunities=opportunities,
            decision=decision,
            coverage_report=self._coverage.get_latest(mission_id),
            action_plan=action_plan,
        )


def _latest_event(events: Sequence[AgentEvent], event_type: str) -> AgentEvent | None:
    return next(
        (event for event in reversed(events) if event.event_type == event_type),
        None,
    )


def _metadata(event: AgentEvent | None) -> dict[str, Any]:
    return event.metadata_json if event is not None else {}


def _parse_handoff(event: AgentEvent | None) -> PhaseCHandoff | None:
    payload = _metadata(event).get("handoff")
    if payload is None:
        return None
    try:
        return PhaseCHandoff.model_validate(payload)
    except ValidationError:
        return None


def _parse_decision(event: AgentEvent | None) -> WorkflowDecision | None:
    payload = _metadata(event).get("decision")
    if payload is None:
        return None
    try:
        return WorkflowDecision.model_validate(payload)
    except ValidationError:
        return None


def _unique(values: Iterable[UniqueValue]) -> list[UniqueValue]:
    return list(dict.fromkeys(values))


def _build_audit(
    handoff: PhaseCHandoff | None,
    *,
    highest_opportunity_score: float | None,
) -> MissionAuditReport | None:
    if handoff is None:
        return None

    sufficiency = handoff.evidence_sufficiency
    support_ids = (
        [item.evidence_id for item in sufficiency.assessments if item.eligible]
        if sufficiency
        else []
    )
    challenge_ids = (
        [
            item.evidence_id
            for item in sufficiency.assessments
            if item.challenge_eligible
        ]
        if sufficiency
        else []
    )
    support_id_set = set(support_ids)
    excluded = (
        [
            item
            for item in sufficiency.assessments
            if not item.eligible and not item.challenge_eligible
        ]
        if sufficiency
        else []
    )
    claims = handoff.claim_assessments
    opposing_ids = _unique(
        evidence_id for claim in claims for evidence_id in claim.opposing_evidence_ids
    )
    verdict_counts = count_verdicts([claim.verdict for claim in claims])
    findings = _audit_findings(
        handoff=handoff,
        opposing_evidence_ids=opposing_ids,
        verdict_counts=verdict_counts,
    )
    status = "pass"
    if handoff.status != "ready_for_poc" or (
        sufficiency is not None and not sufficiency.sufficient
    ):
        status = "insufficient"
    elif findings:
        status = "needs_review"

    return MissionAuditReport(
        status=status,
        phase_c_status=handoff.status,
        phase_c_reason=handoff.reason,
        evidence_sufficiency=sufficiency,
        support_eligible_evidence_ids=support_ids,
        challenge_eligible_evidence_ids=challenge_ids,
        challenge_only_evidence_ids=[
            evidence_id
            for evidence_id in challenge_ids
            if evidence_id not in support_id_set
        ],
        accepted_evidence_ids=_unique([*support_ids, *challenge_ids]),
        excluded_evidence=excluded,
        supporting_evidence_ids=_unique(
            evidence_id
            for claim in claims
            for evidence_id in claim.supporting_evidence_ids
        ),
        opposing_evidence_ids=opposing_ids,
        claim_verdict_counts=verdict_counts,
        unresolved_questions=_unique(
            question
            for candidate in handoff.poc_candidates
            for question in candidate.unresolved_questions
        ),
        highest_opportunity_score=highest_opportunity_score,
        findings=findings,
    )


def _audit_findings(
    *,
    handoff: PhaseCHandoff,
    opposing_evidence_ids: Sequence[UUID],
    verdict_counts: ClaimVerdictCounts,
) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    sufficiency = handoff.evidence_sufficiency
    if sufficiency is not None and not sufficiency.sufficient:
        findings.append(
            AuditFinding(
                severity="blocker",
                code="insufficient_evidence_pool",
                message="The evidence pool did not satisfy the Phase C entry gate.",
            )
        )
    if sufficiency is not None and sufficiency.result_bearing_count == 0:
        findings.append(
            AuditFinding(
                severity="warning",
                code="no_result_bearing_evidence",
                message="No eligible evidence card records an experimental result.",
            )
        )
    if (
        sufficiency is not None
        and sufficiency.total_evidence_count > 0
        and sum(
            item.eligible or item.challenge_eligible for item in sufficiency.assessments
        )
        * 2
        < sufficiency.total_evidence_count
    ):
        findings.append(
            AuditFinding(
                severity="warning",
                code="most_evidence_excluded",
                message=(
                    "More than half of the collected evidence was excluded from "
                    "both support and challenge use."
                ),
            )
        )
    settled_count = (
        verdict_counts.supported + verdict_counts.contested + verdict_counts.refuted
    )
    if handoff.claim_assessments and settled_count == 0:
        findings.append(
            AuditFinding(
                severity="warning",
                code="all_claims_unknown",
                message="Every evaluated claim remains unknown.",
            )
        )
    if handoff.claim_assessments and not opposing_evidence_ids:
        findings.append(
            AuditFinding(
                severity="warning",
                code="no_counterevidence",
                message="No claim assessment cites opposing evidence.",
            )
        )
    return findings
