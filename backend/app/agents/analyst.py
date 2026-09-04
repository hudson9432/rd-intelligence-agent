"""Evidence-grounded feasible-direction selection."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from app.schemas.analysis import AnalystOutcome, DirectionDraft, RankedDirection
from app.schemas.evidence_card import EvidenceCard
from app.services.scoring import direction_evidence_coverage, evidence_index


class DirectionGenerator(Protocol):
    """Provider boundary implemented by an LLM adapter or deterministic mock."""

    def generate_directions(
        self, *, mission_goal: str, evidence: Sequence[EvidenceCard]
    ) -> Sequence[DirectionDraft]: ...


class AnalystAgent:
    """Generate, validate, rank, and retain feasible research directions."""

    def __init__(
        self,
        generator: DirectionGenerator,
        *,
        max_active_directions: int = 4,
        max_generated_directions: int = 12,
    ) -> None:
        if not 1 <= max_active_directions <= 4:
            raise ValueError("max_active_directions must be between 1 and 4")
        if max_generated_directions < max_active_directions:
            raise ValueError(
                "max_generated_directions cannot be smaller than max_active_directions"
            )
        self.generator = generator
        self.max_active_directions = max_active_directions
        self.max_generated_directions = max_generated_directions

    def analyze(
        self, *, mission_goal: str, evidence: Sequence[EvidenceCard]
    ) -> AnalystOutcome:
        if not mission_goal.strip():
            raise ValueError("mission_goal cannot be empty")
        if not evidence:
            return AnalystOutcome(
                status="research_required",
                reason="No evidence is available to support a feasible direction.",
            )

        evidence_by_id = evidence_index(evidence)
        drafts = list(
            self.generator.generate_directions(
                mission_goal=mission_goal,
                evidence=evidence,
            )
        )[: self.max_generated_directions]

        scored_by_title: dict[str, tuple[DirectionDraft, float]] = {}
        for draft in drafts:
            normalized_title = " ".join(draft.title.casefold().split())
            coverage = direction_evidence_coverage(draft, evidence_by_id)
            current = scored_by_title.get(normalized_title)
            if coverage > 0 and (
                current is None
                or coverage > current[1]
                or (coverage == current[1] and draft.id < current[0].id)
            ):
                scored_by_title[normalized_title] = (draft, coverage)

        scored = list(scored_by_title.values())
        if not scored:
            return AnalystOutcome(
                status="research_required",
                reason="Generated directions have no traceable supporting evidence.",
            )

        scored.sort(key=lambda item: (-item[1], item[0].title.casefold(), item[0].id))
        ranked = [
            RankedDirection(
                **draft.model_dump(),
                evidence_coverage=coverage,
                rank=index,
            )
            for index, (draft, coverage) in enumerate(scored, start=1)
        ]
        return AnalystOutcome(
            status="ready",
            active_directions=ranked[: self.max_active_directions],
            candidate_directions=ranked[self.max_active_directions :],
        )
