"""Narrow persistence boundary between B's extraction and C's analysis."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from app.schemas.evidence_card import EvidenceCard, EvidenceCardCreate


class EvidenceCardWriter(Protocol):
    """Small repository surface needed by the B-to-C bridge."""

    def save(self, data: EvidenceCardCreate) -> object: ...


def persist_evidence_for_analysis(
    *,
    extracted: Sequence[EvidenceCardCreate],
    writer: EvidenceCardWriter,
) -> list[EvidenceCard]:
    """Persist B outputs and return C-ready cards with stable evidence IDs.

    C must never analyze an unpersisted extraction because recommendations
    require stable evidence IDs. Mixed-mission batches are rejected before any
    write occurs.
    """

    mission_ids = {card.mission_id for card in extracted}
    if len(mission_ids) > 1:
        raise ValueError("Extracted evidence batch must belong to one mission")

    persisted: list[EvidenceCard] = []
    for card in extracted:
        record = writer.save(card)
        persisted_card = EvidenceCard.model_validate(record)
        if persisted_card.mission_id != card.mission_id:
            raise ValueError("Persisted evidence changed mission provenance")
        if persisted_card.source_id != card.source_id:
            raise ValueError("Persisted evidence changed source provenance")
        persisted.append(persisted_card)
    return persisted
