"""Source document persistence operations."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SourceDocument
from app.schemas.source_document import SourceDocumentCreate


class SourceDocumentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, data: SourceDocumentCreate) -> SourceDocument:
        source = SourceDocument(
            mission_id=str(data.mission_id),
            source_type=data.source_type,
            title=data.title,
            url=data.url,
            published_at=data.published_at,
            authors_json=data.authors_json,
            raw_summary=data.raw_summary,
            content=data.content,
            content_hash=data.content_hash,
        )
        self.session.add(source)
        self.session.commit()
        self.session.refresh(source)
        return source

    def list_for_mission(self, mission_id: UUID | str) -> list[SourceDocument]:
        statement = (
            select(SourceDocument)
            .where(SourceDocument.mission_id == str(mission_id))
            .order_by(SourceDocument.created_at, SourceDocument.id)
        )
        return list(self.session.scalars(statement))

    def delete(self, source: SourceDocument) -> None:
        self.session.delete(source)
        self.session.commit()
