"""Coverage report persistence operations."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CoverageReport
from app.schemas.coverage_report import CoverageReportCreate


class CoverageReportRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, data: CoverageReportCreate) -> CoverageReport:
        statement = select(CoverageReport).where(
            CoverageReport.mission_id == str(data.mission_id),
            CoverageReport.iteration == data.iteration,
        )
        report = self.session.scalar(statement)
        values = {
            "overall_score": data.overall_score,
            "sufficient": data.sufficient,
            "dimension_status_json": data.dimension_status_json,
            "missing_evidence_json": data.missing_evidence_json,
            "unsupported_claims_json": data.unsupported_claims_json,
            "suggested_queries_json": data.suggested_queries_json,
        }
        if report is None:
            report = CoverageReport(
                mission_id=str(data.mission_id),
                iteration=data.iteration,
                **values,
            )
            self.session.add(report)
        else:
            for field, value in values.items():
                setattr(report, field, value)
        self.session.commit()
        self.session.refresh(report)
        return report

    def get_latest(self, mission_id: UUID | str) -> CoverageReport | None:
        statement = (
            select(CoverageReport)
            .where(CoverageReport.mission_id == str(mission_id))
            .order_by(CoverageReport.iteration.desc(), CoverageReport.created_at.desc())
            .limit(1)
        )
        return self.session.scalar(statement)
