"""Evidence Agent: turns a normalized source result into structured evidence."""

from __future__ import annotations

import re

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.llm import LLMClient
from app.prompts.evidence import build_evidence_messages
from app.schemas.evidence_card import EvidenceCardCreate
from app.schemas.source_result import SourceResult
from app.services.scoring import goal_overlap


#: Phrases that mark a sentence as stating a scope limit or caveat. Kept
#: explicit so the match is auditable rather than a general-purpose classifier.
_LIMITATION_MARKERS = (
    "limitation",
    "limited to",
    "is limited",
    "however",
    "only",
    "does not",
    "do not",
    "did not",
    "cannot",
    "not evaluated",
    "restricted to",
    "future work",
    "remains an open",
)

_MAX_LIMITATION_CHARS = 300

_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")


def stated_limitation(source_text: str) -> str | None:
    """Return the first sentence of the source that states a limitation.

    Extraction, never invention: the returned text is a verbatim span of the
    source, so `_validate_provenance` can confirm it. If the source states no
    caveat, the field stays null — invariant 3 keeps unknown fields empty
    rather than guessed.
    """

    for sentence in _SENTENCE_BREAK.split(source_text):
        candidate = sentence.strip()
        if not candidate:
            continue
        lowered = candidate.lower()
        if any(marker in lowered for marker in _LIMITATION_MARKERS):
            return candidate[:_MAX_LIMITATION_CHARS]
    return None


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
        self,
        *,
        mission_id: UUID,
        source_id: UUID,
        source: SourceResult,
        mission_goal: str,
    ) -> EvidenceCardCreate:
        """Extract structured evidence from one source, scored against the goal.

        `mission_goal` is required because `relevance_score` has no meaning
        without it — it rates how much this source bears on what the mission is
        trying to decide.
        """

        messages = build_evidence_messages(source, mission_goal=mission_goal)
        completion = self._llm_client.complete(messages)

        try:
            extraction = EvidenceExtraction.model_validate_json(completion.content)
        except ValidationError as error:
            if not completion.mocked:
                raise EvidenceExtractionError(
                    "LLM response could not be parsed into structured evidence"
                ) from error
            extraction = self._deterministic_mock_extraction(source, mission_goal)

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
    def _deterministic_mock_extraction(
        source: SourceResult, mission_goal: str
    ) -> EvidenceExtraction:
        """Synthesize evidence directly from the source for offline demo mode.

        Used only when the LLM client is the deterministic mock, whose text
        response is not parseable JSON. Every field is copied verbatim from the
        source, so the same source and goal always yield the same evidence and
        nothing is invented.

        `relevance_score` comes from deterministic lexical overlap with the
        mission goal. It used to be a hard zero, which was safe but made every
        resulting direction fail Phase C's evidence-coverage check, so an
        offline run could never reach a PoC candidate. Overlap is a shallow
        stand-in for a model's judgement, not a semantic measure.

        `extraction_confidence` stays at 1.0 because every field emitted here
        is source text copied verbatim. That rates fidelity, not completeness:
        the mock leaves problem, method, benchmark, and result unset rather
        than guessing at them.
        """

        source_text = source.content or source.summary or source.title
        snippets = [source_text[:200]] if source_text else []

        limitation = stated_limitation(source_text) if source_text else None
        if limitation is not None and limitation not in snippets:
            # Keep the quote in the snippet list so provenance stays checkable.
            snippets.append(limitation)

        return EvidenceExtraction(
            limitation=limitation,
            evidence_snippets=snippets,
            relevance_score=goal_overlap(mission_goal, source_text or ""),
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
