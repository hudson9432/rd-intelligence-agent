"""Evidence extraction and persistence wired as a workflow stage.

Phase 06. Turns the sources a round retrieved into evidence the Analyst can
cite, doing the four things the roadmap asks of this phase:

- **deduplicate** against evidence the mission already holds, by source URL,
  so a re-search round does not re-extract what is already stored;
- **filter** out sources whose extraction fails its provenance checks, so one
  bad source degrades a round instead of failing the run;
- **persist** the source and then the evidence, because stable evidence ids
  come from persistence and never from the model — `docs/BC_INTEGRATION.md`;
- leave **events** to the orchestrator, which already reports each round.

Sources are persisted before extraction: an `EvidenceCard` needs a `source_id`,
and provenance has to point at a row that exists.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.orm import Session

from app.agents.evidence import EvidenceAgent, EvidenceExtractionError
from app.core.config import Settings, get_settings
from app.core.llm import LLMClient, get_llm_client
from app.repositories.evidence_card import EvidenceCardRepository
from app.repositories.source_document import SourceDocumentRepository
from app.schemas.evidence_card import EvidenceCard, EvidenceCardCreate
from app.schemas.source_document import SourceDocumentCreate
from app.schemas.source_result import SourceResult
from app.services.evidence_analysis import persist_evidence_for_analysis
from app.tools.dedupe import content_hash, normalize_url

logger = logging.getLogger(__name__)


class PersistingEvidenceStage:
    """Extracts evidence from sources and stores both."""

    def __init__(
        self,
        session: Session,
        *,
        llm_client: LLMClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._sources = SourceDocumentRepository(session)
        self._evidence = EvidenceCardRepository(session)
        self._agent = EvidenceAgent(
            llm_client or get_llm_client(settings or get_settings())
        )

    def extract(
        self, *, mission_id: UUID, goal: str, sources: Sequence[SourceResult]
    ) -> Sequence[EvidenceCard]:
        if not sources:
            return []

        stored_urls = {
            normalize_url(document.url)
            for document in self._sources.list_for_mission(mission_id)
        }

        extracted: list[EvidenceCardCreate] = []
        for source in sources:
            if normalize_url(source.url) in stored_urls:
                continue
            stored_urls.add(normalize_url(source.url))

            document = self._sources.save(self._to_document(mission_id, source))
            try:
                extracted.append(
                    self._agent.extract(
                        mission_id=mission_id,
                        source_id=UUID(document.id),
                        source=source,
                        mission_goal=goal,
                    )
                )
            except EvidenceExtractionError:
                # The source stays stored as a record of what was retrieved,
                # but nothing unverifiable enters the evidence pool.
                logger.warning(
                    "Evidence extraction rejected source %s for mission %s",
                    source.url,
                    mission_id,
                    exc_info=True,
                )

        if not extracted:
            return []

        return persist_evidence_for_analysis(
            extracted=extracted, writer=self._evidence
        )

    @staticmethod
    def _to_document(
        mission_id: UUID, source: SourceResult
    ) -> SourceDocumentCreate:
        return SourceDocumentCreate(
            mission_id=mission_id,
            source_type=source.source_type,
            title=source.title[:500],
            url=source.url,
            published_at=source.published_at,
            authors_json=list(source.authors),
            raw_summary=source.summary,
            content=source.content,
            # The same hash the source tools deduplicate on, so a stored
            # document and a fresh result agree on identity.
            content_hash=content_hash(
                source.title, source.summary or "", source.content or ""
            ),
        )
