"""Evidence card persistence operations with provenance validation."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EvidenceCard, SourceDocument
from app.schemas.evidence_card import EvidenceCardCreate


class EvidenceCardRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, data: EvidenceCardCreate) -> EvidenceCard:
        mission_id = str(data.mission_id)
        source = self.session.get(SourceDocument, str(data.source_id))
        if source is None or source.mission_id != mission_id:
            raise ValueError("Evidence source must belong to the same mission")

        evidence = EvidenceCard(
            mission_id=mission_id,
            source_id=str(data.source_id),
            problem=data.problem,
            method=data.method,
            benchmark=data.benchmark,
            result=data.result,
            limitation=data.limitation,
            technology_tags_json=data.technology_tags_json,
            evidence_snippets_json=data.evidence_snippets_json,
            relevance_score=data.relevance_score,
            extraction_confidence=data.extraction_confidence,
        )
        self.session.add(evidence)
        self.session.commit()
        self.session.refresh(evidence)
        return evidence

    def list_for_mission(self, mission_id: UUID | str) -> list[EvidenceCard]:
        statement = (
            select(EvidenceCard)
            .where(EvidenceCard.mission_id == str(mission_id))
            .order_by(EvidenceCard.created_at, EvidenceCard.id)
        )
        return list(self.session.scalars(statement))
