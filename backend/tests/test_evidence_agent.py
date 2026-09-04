"""Tests for the Evidence Agent."""

from uuid import uuid4

import pytest

from app.agents.evidence import EvidenceAgent, EvidenceExtractionError
from app.core.llm import LLMClient, MockLLMClient
from app.schemas.llm import LLMCompletion, LLMMessage
from app.schemas.source_result import SourceResult


class _StubLLMClient(LLMClient):
    def __init__(self, content: str, *, mocked: bool = False) -> None:
        self._content = content
        self._mocked = mocked

    def complete(self, messages: list[LLMMessage]) -> LLMCompletion:
        del messages
        return LLMCompletion(content=self._content, model="stub", mocked=self._mocked)


def _source(**overrides: object) -> SourceResult:
    defaults: dict[str, object] = {
        "source_type": "arxiv",
        "title": "Recovering from failed GUI actions",
        "url": "https://arxiv.org/abs/9999.99999",
        "raw_summary": "A short summary of the paper.",
        "content": "The paper studies recovery loops for computer-use agents.",
        "content_hash": "a" * 64,
    }
    defaults.update(overrides)
    return SourceResult(**defaults)


def test_extract_parses_valid_structured_response() -> None:
    content = (
        '{"problem": "Agents fail silently", "method": "Retry loop", '
        '"benchmark": null, "result": null, "limitation": null, '
        '"technology_tags": ["recovery"], "evidence_snippets": ["quote"], '
        '"relevance_score": 0.8, "extraction_confidence": 0.9}'
    )
    agent = EvidenceAgent(_StubLLMClient(content))
    mission_id, source_id = uuid4(), uuid4()

    evidence = agent.extract(mission_id=mission_id, source_id=source_id, source=_source())

    assert evidence.mission_id == mission_id
    assert evidence.source_id == source_id
    assert evidence.problem == "Agents fail silently"
    assert evidence.technology_tags_json == ["recovery"]
    assert evidence.relevance_score == 0.8


def test_extract_raises_on_malformed_real_response() -> None:
    agent = EvidenceAgent(_StubLLMClient("not json", mocked=False))

    with pytest.raises(EvidenceExtractionError):
        agent.extract(mission_id=uuid4(), source_id=uuid4(), source=_source())


def test_extract_falls_back_to_deterministic_mock_for_mocked_completions() -> None:
    agent = EvidenceAgent(_StubLLMClient("not json", mocked=True))
    source = _source()

    first = agent.extract(mission_id=uuid4(), source_id=uuid4(), source=source)
    second = agent.extract(mission_id=uuid4(), source_id=uuid4(), source=source)

    assert first.relevance_score == second.relevance_score
    assert first.extraction_confidence == second.extraction_confidence
    assert 0 <= first.relevance_score <= 1
    assert first.evidence_snippets_json


def test_extract_end_to_end_with_mock_llm_client() -> None:
    agent = EvidenceAgent(MockLLMClient())
    mission_id, source_id = uuid4(), uuid4()

    evidence = agent.extract(mission_id=mission_id, source_id=source_id, source=_source())

    assert evidence.mission_id == mission_id
    assert evidence.source_id == source_id
    assert 0 <= evidence.relevance_score <= 1
