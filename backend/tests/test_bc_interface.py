"""Integration tests for the narrow B-to-C boundary."""

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from inspect import signature
from uuid import uuid4

import pytest

from app.agents.analysis_llm import (
    DIRECTION_BATCH_CEILING,
    QUESTION_BATCH_CEILING,
    AnalysisGenerationError,
    LLMAnalysisAdapter,
)
from app.agents.analyst import AnalystAgent
from app.agents.critic import CriticAgent
from app.agents.evidence import EvidenceAgent
from app.core.llm import LLMClient, MockLLMClient
from app.schemas.evidence_card import EvidenceCard, EvidenceCardCreate
from app.schemas.llm import LLMCompletion, LLMMessage
from app.schemas.source_result import SourceResult
from app.services.evidence_analysis import persist_evidence_for_analysis
from app.services.phase_c import build_phase_c_handoff


class MemoryEvidenceWriter:
    def __init__(self) -> None:
        self.saved: list[EvidenceCardCreate] = []

    def save(self, data: EvidenceCardCreate) -> EvidenceCard:
        self.saved.append(data)
        return EvidenceCard(
            **data.model_dump(),
            id=uuid4(),
            created_at=datetime.now(UTC),
        )


class FixedLLMClient(LLMClient):
    """Replays scripted responses, repeating the last once they run out.

    A structured call may ask more than once when a response does not match
    its contract, so a double that runs dry would fail on the attempt count
    rather than on the behaviour under test.
    """

    def __init__(self, responses: Sequence[str]) -> None:
        self.responses = list(responses)
        self.calls = 0

    def complete(self, messages: list[LLMMessage]) -> LLMCompletion:
        assert messages
        index = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        return LLMCompletion(
            content=self.responses[index],
            model="fixed",
            mocked=False,
        )


def evidence_create(*, mission_id=None, source_id=None) -> EvidenceCardCreate:
    return EvidenceCardCreate(
        mission_id=mission_id or uuid4(),
        source_id=source_id or uuid4(),
        problem="Shoppers have difficulty comparing complex products.",
        method="A grounded conversational recommender.",
        result="The hybrid system improves recommendation relevance.",
        limitation="The evaluation covers only one product category.",
        technology_tags_json=["conversational-commerce"],
        evidence_snippets_json=["The hybrid system improves relevance."],
        relevance_score=0.9,
        extraction_confidence=0.9,
    )


def test_bridge_persists_b_output_before_c_receives_evidence_ids() -> None:
    mission_id = uuid4()
    extracted = [
        evidence_create(mission_id=mission_id),
        evidence_create(mission_id=mission_id),
    ]
    writer = MemoryEvidenceWriter()

    ready = persist_evidence_for_analysis(extracted=extracted, writer=writer)

    assert len(writer.saved) == 2
    assert len(ready) == 2
    assert all(card.id for card in ready)
    assert [card.source_id for card in ready] == [card.source_id for card in extracted]


def test_bridge_rejects_mixed_missions_before_writing() -> None:
    writer = MemoryEvidenceWriter()

    with pytest.raises(ValueError, match="one mission"):
        persist_evidence_for_analysis(
            extracted=[evidence_create(), evidence_create()],
            writer=writer,
        )

    assert not writer.saved


def test_real_llm_adapter_rejects_malformed_structured_output() -> None:
    mission_id = uuid4()
    writer = MemoryEvidenceWriter()
    evidence = persist_evidence_for_analysis(
        extracted=[evidence_create(mission_id=mission_id)],
        writer=writer,
    )
    adapter = LLMAnalysisAdapter(FixedLLMClient(["not-json"]))

    with pytest.raises(AnalysisGenerationError, match="direction-generation"):
        adapter.generate_directions(
            mission_goal="Find an e-commerce extension.",
            evidence=evidence,
        )


def test_b_evidence_agent_connects_to_c_and_produces_poc_handoff() -> None:
    mission_id = uuid4()
    source_id = uuid4()
    extraction_json = (
        '{"problem":"Shoppers have difficulty comparing products",'
        '"method":"A grounded conversational recommender",'
        '"benchmark":"Offline recommendation benchmark",'
        '"result":"The hybrid system improves recommendation relevance",'
        '"limitation":"The evaluation covers only one product category",'
        '"technology_tags":["conversational-commerce"],'
        '"evidence_snippets":["The hybrid system improves recommendation relevance"],'
        '"relevance_score":0.9,"extraction_confidence":0.9}'
    )
    extracted = EvidenceAgent(FixedLLMClient([extraction_json])).extract(
        mission_id=mission_id,
        source_id=source_id,
        mission_goal="Improve grounded conversational product recommendation.",
        source=SourceResult(
            source_type="arxiv",
            title="Hybrid conversational recommendation",
            url="https://example.test/research",
            content=(
                "The hybrid system improves recommendation relevance. "
                "The evaluation covers only one product category."
            ),
        ),
    )
    writer = MemoryEvidenceWriter()
    evidence = persist_evidence_for_analysis(
        extracted=[extracted],
        writer=writer,
    )
    adapter = LLMAnalysisAdapter(MockLLMClient())

    analysis = AnalystAgent(adapter).analyze(
        mission_goal="Find an e-commerce extension.",
        evidence=evidence,
    )
    critique = CriticAgent(adapter, adapter).critique(
        mission_goal="Find an e-commerce extension.",
        analysis=analysis,
        evidence=evidence,
    )
    reviews = adapter.review_claims(
        analysis=analysis,
        critique=critique,
        evidence=evidence,
    )
    handoff = build_phase_c_handoff(
        mission_goal="Find an e-commerce extension.",
        analysis=analysis,
        critique=critique,
        evidence=evidence,
        claim_reviews=reviews,
    )

    assert analysis.status == "ready"
    assert critique.status == "ready"
    assert handoff.status == "ready_for_poc"
    assert handoff.poc_candidates[0].evidence_ids == [evidence[0].id]


def test_over_limit_question_batch_is_trimmed_rather_than_rejected() -> None:
    """A batch a little over the working limit must not fail the workflow.

    The Critic slices candidates to its own limit on the next line, so
    rejecting the batch would discard every earlier retrieval and extraction
    to save questions that were going to be dropped anyway.
    """

    over_limit = 26  # what a real provider returned against a limit of 24
    payload = json.dumps(
        {
            "questions": [
                {
                    "id": f"Q-{index}",
                    "direction_id": "D1",
                    "challenged_claim_id": "C1",
                    "question": f"Does claim C1 hold under condition {index}?",
                    "rationale": "The supplied evidence does not settle it.",
                    "evidence_ids": [],
                    "suggested_query": None,
                }
                for index in range(over_limit)
            ]
        }
    )
    client = FixedLLMClient([payload])
    adapter = LLMAnalysisAdapter(client)

    questions = adapter.generate_questions(
        mission_goal="Find an e-commerce extension.",
        directions=[],
        evidence=[],
    )

    assert len(questions) == over_limit
    assert client.calls == 1, "a valid batch must not be asked for twice"


def test_batch_ceilings_leave_headroom_above_the_working_limits() -> None:
    """The schema bound must not sit on the limit the agents slice to.

    Reading the defaults off the signatures keeps this honest if either limit
    is raised later: the ceilings have to move with them.
    """

    critic_limit = signature(CriticAgent).parameters["max_candidate_questions"].default
    analyst_limit = (
        signature(AnalystAgent).parameters["max_generated_directions"].default
    )

    assert QUESTION_BATCH_CEILING > critic_limit
    assert DIRECTION_BATCH_CEILING > analyst_limit
