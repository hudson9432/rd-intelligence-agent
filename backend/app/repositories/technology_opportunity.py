"""Technology opportunity persistence operations."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EvidenceCard, TechnologyOpportunity
from app.schemas.technology_opportunity import TechnologyOpportunityCreate


class TechnologyOpportunityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, data: TechnologyOpportunityCreate) -> TechnologyOpportunity:
        mission_id = str(data.mission_id)
        evidence_ids = [
            str(evidence_id) for evidence_id in data.related_evidence_ids_json
        ]
        if evidence_ids:
            statement = select(EvidenceCard.id).where(
                EvidenceCard.id.in_(evidence_ids),
                EvidenceCard.mission_id == mission_id,
            )
            matching_ids = set(self.session.scalars(statement))
            if matching_ids != set(evidence_ids):
                raise ValueError("Opportunity evidence must belong to the same mission")

        opportunity = TechnologyOpportunity(
            mission_id=mission_id,
            name=data.name,
            description=data.description,
            related_evidence_ids_json=evidence_ids,
            novelty=data.novelty,
            technical_maturity=data.technical_maturity,
            implementation_difficulty=data.implementation_difficulty,
            goal_alignment=data.goal_alignment,
            poc_feasibility=data.poc_feasibility,
            evidence_strength=data.evidence_strength,
            overall_score=data.overall_score,
            rationale=data.rationale,
        )
        self.session.add(opportunity)
        self.session.commit()
        self.session.refresh(opportunity)
        return opportunity

    def replace_for_mission(
        self, mission_id: UUID | str, opportunities: list[TechnologyOpportunityCreate]
    ) -> list[TechnologyOpportunity]:
        """Store one scoring round, discarding the previous one.

        `save` only ever inserts, so a re-run would otherwise leave two
        generations of scores side by side with nothing saying which is
        current.
        """

        for existing in self.list_for_mission(mission_id):
            self.session.delete(existing)
        self.session.flush()
        return [self.save(opportunity) for opportunity in opportunities]

    def list_for_mission(self, mission_id: UUID | str) -> list[TechnologyOpportunity]:
        statement = (
            select(TechnologyOpportunity)
            .where(TechnologyOpportunity.mission_id == str(mission_id))
            .order_by(
                TechnologyOpportunity.overall_score.desc(),
                TechnologyOpportunity.created_at,
            )
        )
        return list(self.session.scalars(statement))
