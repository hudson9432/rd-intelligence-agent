"""Evidence Agent: turns a normalized source result into structured evidence."""

from __future__ import annotations

import hashlib
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError

from app.core.llm import LLMClient
from app.prompts.evidence import build_evidence_messages
from app.schemas.evidence_card import EvidenceCardCreate
from app.schemas.source_result import SourceResult


class EvidenceExtractionError(RuntimeError):
    """Raised when a real LLM response cannot be parsed into evidence."""


class EvidenceExtraction(BaseModel):
    """Structured shape requested from the LLM before it becomes an EvidenceCard."""

    problem: str | None = None
    method: str | None = None
    benchmark: str | None = None
    result: str | None = None
    limitation: str | None = None
    technology_tags: list[str] = Field(default_factory=list)
    evidence_snippets: list[str] = Field(default_factory=list)
    relevance_score: float = Field(ge=0, le=1)
    extraction_confidence: float = Field(ge=0, le=1)


class EvidenceAgent:
    """Extracts a structured, source-linked EvidenceCard using an LLMClient."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    def extract(
        self, *, mission_id: UUID, source_id: UUID, source: SourceResult
    ) -> EvidenceCardCreate:
        messages = build_evidence_messages(source)
        completion = self._llm_client.complete(messages)

        try:
            extraction = EvidenceExtraction.model_validate_json(completion.content)
        except ValidationError as error:
            if not completion.mocked:
                raise EvidenceExtractionError(
                    "LLM response could not be parsed into structured evidence"
                ) from error
            extraction = self._deterministic_mock_extraction(source)

        return EvidenceCardCreate(
            mission_id=mission_id,
            source_id=source_id,
            problem=extraction.problem,
            method=extraction.method,
            benchmark=extraction.benchmark,
            result=extraction.result,
            limitation=extraction.limitation,
            technology_tags_json=extraction.technology_tags,
            evidence_snippets_json=extraction.evidence_snippets,
            relevance_score=extraction.relevance_score,
            extraction_confidence=extraction.extraction_confidence,
        )

    @staticmethod
    def _deterministic_mock_extraction(source: SourceResult) -> EvidenceExtraction:
        """Synthesize evidence directly from the source for offline demo mode.

        Used only when the LLM client is the deterministic mock, whose text
        response is not parseable JSON. Every field is derived solely from the
        source, so the same source always yields the same evidence.
        """

        digest = hashlib.sha256(source.content_hash.encode("utf-8")).hexdigest()
        score = int(digest[:4], 16) / 0xFFFF
        snippet_source = source.content or source.raw_summary or source.title
        snippet = snippet_source[:200]

        return EvidenceExtraction(
            problem=f"Mock-extracted problem statement from: {source.title}",
            technology_tags=[source.source_type],
            evidence_snippets=[snippet] if snippet else [],
            relevance_score=round(score, 4),
            extraction_confidence=round(score, 4),
        )
