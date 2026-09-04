"""Evidence Agent: turns a normalized source result into structured evidence."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.llm import LLMClient
from app.prompts.evidence import build_evidence_messages
from app.schemas.evidence_card import EvidenceCardCreate
from app.schemas.source_result import SourceResult


class EvidenceExtractionError(RuntimeError):
    """Raised when an LLM response is invalid or lacks source provenance."""


class EvidenceExtraction(BaseModel):
    """Structured shape requested from the LLM before it becomes an EvidenceCard."""

    model_config = ConfigDict(extra="forbid")

    problem: str | None = None
    method: str | None = None
    benchmark: str | None = None
    result: str | None = None
    limitation: str | None = None
    technology_tags: list[Annotated[str, Field(min_length=1)]] = Field(
        default_factory=list
    )
    evidence_snippets: list[Annotated[str, Field(min_length=1)]] = Field(
        default_factory=list
    )
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

        self._validate_provenance(extraction, source)

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

        snippet_source = source.content or source.summary or source.title
        snippet = snippet_source[:200]

        return EvidenceExtraction(
            evidence_snippets=[snippet] if snippet else [],
            relevance_score=0,
            extraction_confidence=1,
        )

    @staticmethod
    def _validate_provenance(
        extraction: EvidenceExtraction, source: SourceResult
    ) -> None:
        """Reject quotes that are absent from the supplied source text."""

        source_fields = tuple(
            value
            for value in (source.title, source.summary, source.content)
            if value is not None
        )
        unsupported_snippets = [
            snippet
            for snippet in extraction.evidence_snippets
            if not any(snippet in source_field for source_field in source_fields)
        ]
        if unsupported_snippets:
            raise EvidenceExtractionError(
                "LLM response contained evidence snippets absent from the source"
            )

        factual_fields = (
            extraction.problem,
            extraction.method,
            extraction.benchmark,
            extraction.result,
            extraction.limitation,
        )
        if (
            any(value is not None for value in factual_fields)
            and not extraction.evidence_snippets
        ):
            raise EvidenceExtractionError(
                "LLM response contained factual claims without source evidence snippets"
            )
