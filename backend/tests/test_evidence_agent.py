"""Tests for the Evidence Agent."""

from uuid import uuid4

import pytest

from app.agents.evidence import EvidenceAgent, EvidenceExtractionError
from app.core.llm import LLMClient, MockLLMClient
from app.schemas.llm import LLMCompletion, LLMMessage
from app.schemas.source_result import SourceResult

GOAL = "Improve recovery from failed GUI actions in computer-use agents."


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
        "summary": "A short summary of the paper.",
        "content": "The paper studies recovery loops for computer-use agents.",
    }
    defaults.update(overrides)
    return SourceResult(**defaults)


def test_extract_parses_valid_structured_response() -> None:
    content = (
        '{"problem": "Agents fail silently", "method": "Retry loop", '
        '"benchmark": null, "result": null, "limitation": null, '
        '"technology_tags": ["recovery"], '
        '"evidence_snippets": ["recovery loops"], '
        '"relevance_score": 0.8, "extraction_confidence": 0.9}'
    )
    agent = EvidenceAgent(_StubLLMClient(content))
    mission_id, source_id = uuid4(), uuid4()

    evidence = agent.extract(
        mission_id=mission_id,
        source_id=source_id,
        source=_source(),
        mission_goal=GOAL,
    )

    assert evidence.mission_id == mission_id
    assert evidence.source_id == source_id
    assert evidence.problem == "Agents fail silently"
    assert evidence.technology_tags_json == ["recovery"]
    assert evidence.relevance_score == 0.8


def test_extract_raises_on_malformed_real_response() -> None:
    agent = EvidenceAgent(_StubLLMClient("not json", mocked=False))

    with pytest.raises(EvidenceExtractionError):
        agent.extract(
            mission_id=uuid4(),
            source_id=uuid4(),
            source=_source(),
            mission_goal=GOAL,
        )


def test_extract_rejects_quote_absent_from_source() -> None:
    content = (
        '{"problem": "Agents fail silently", "method": null, '
        '"benchmark": null, "result": null, "limitation": null, '
        '"technology_tags": [], "evidence_snippets": ["fabricated quote"], '
        '"relevance_score": 0.8, "extraction_confidence": 0.9}'
    )
    agent = EvidenceAgent(_StubLLMClient(content))

    with pytest.raises(EvidenceExtractionError, match="absent from the source"):
        agent.extract(
            mission_id=uuid4(),
            source_id=uuid4(),
            source=_source(),
            mission_goal=GOAL,
        )


def test_extract_rejects_claims_without_source_snippets() -> None:
    content = (
        '{"problem": "Agents fail silently", "method": null, '
        '"benchmark": null, "result": null, "limitation": null, '
        '"technology_tags": [], "evidence_snippets": [], '
        '"relevance_score": 0.8, "extraction_confidence": 0.9}'
    )
    agent = EvidenceAgent(_StubLLMClient(content))

    with pytest.raises(EvidenceExtractionError, match="without source evidence"):
        agent.extract(
            mission_id=uuid4(),
            source_id=uuid4(),
            source=_source(),
            mission_goal=GOAL,
        )


def test_extract_falls_back_to_deterministic_mock_for_mocked_completions() -> None:
    agent = EvidenceAgent(_StubLLMClient("not json", mocked=True))
    source = _source()

    first = agent.extract(
        mission_id=uuid4(), source_id=uuid4(), source=source, mission_goal=GOAL
    )
    second = agent.extract(
        mission_id=uuid4(), source_id=uuid4(), source=source, mission_goal=GOAL
    )

    assert first.relevance_score == second.relevance_score
    assert first.extraction_confidence == second.extraction_confidence
    assert first.problem is None
    # Relevance now tracks overlap with the goal instead of a constant zero,
    # which is what let every Phase C direction fail on evidence coverage.
    assert first.relevance_score > 0
    assert first.extraction_confidence == 1
    assert first.evidence_snippets_json


def test_extract_end_to_end_with_mock_llm_client() -> None:
    agent = EvidenceAgent(MockLLMClient())
    mission_id, source_id = uuid4(), uuid4()

    evidence = agent.extract(
        mission_id=mission_id,
        source_id=source_id,
        source=_source(),
        mission_goal=GOAL,
    )

    assert evidence.mission_id == mission_id
    assert evidence.source_id == source_id
    assert 0 <= evidence.relevance_score <= 1


def test_mock_relevance_tracks_the_goal_rather_than_being_constant() -> None:
    """The old constant zero made every Phase C direction fail on coverage."""

    agent = EvidenceAgent(_StubLLMClient("not json", mocked=True))
    on_topic = _source(
        content="Recovery loops for computer-use agents that retry failed GUI actions."
    )
    off_topic = _source(
        title="Three-field rotation in twelfth-century manorial ledgers",
        summary="A survey of medieval agricultural record keeping.",
        content="Medieval crop rotation practices recorded in manorial ledgers.",
    )

    relevant = agent.extract(
        mission_id=uuid4(), source_id=uuid4(), source=on_topic, mission_goal=GOAL
    )
    unrelated = agent.extract(
        mission_id=uuid4(), source_id=uuid4(), source=off_topic, mission_goal=GOAL
    )

    assert relevant.relevance_score > unrelated.relevance_score
    # Nothing in an off-topic title or body matches the goal's content words.
    assert unrelated.relevance_score == 0


def test_mock_extraction_quotes_a_limitation_stated_by_the_source() -> None:
    agent = EvidenceAgent(_StubLLMClient("not json", mocked=True))
    source = _source(
        content=(
            "The recovery loop repairs failed GUI actions. "
            "However, the evaluation covers only one desktop environment."
        )
    )

    evidence = agent.extract(
        mission_id=uuid4(), source_id=uuid4(), source=source, mission_goal=GOAL
    )

    assert evidence.limitation == (
        "However, the evaluation covers only one desktop environment."
    )
    # Provenance: the quote must be present in the source and in the snippets.
    assert evidence.limitation in (source.content or "")
    assert evidence.limitation in evidence.evidence_snippets_json


def test_mock_extraction_leaves_limitation_null_when_none_is_stated() -> None:
    """Invariant 3: an unknown field stays empty rather than being guessed."""

    agent = EvidenceAgent(_StubLLMClient("not json", mocked=True))
    source = _source(content="The recovery loop repairs failed GUI actions.")

    evidence = agent.extract(
        mission_id=uuid4(), source_id=uuid4(), source=source, mission_goal=GOAL
    )

    assert evidence.limitation is None


def test_mock_extraction_still_invents_no_factual_fields() -> None:
    agent = EvidenceAgent(_StubLLMClient("not json", mocked=True))
    source = _source(
        content="The loop repairs failed actions. However, only one app was tested."
    )

    evidence = agent.extract(
        mission_id=uuid4(), source_id=uuid4(), source=source, mission_goal=GOAL
    )

    assert evidence.problem is None
    assert evidence.method is None
    assert evidence.benchmark is None
    assert evidence.result is None
    assert evidence.technology_tags_json == []


def test_the_prompt_carries_the_mission_goal() -> None:
    """A real provider cannot score relevance without knowing the goal."""

    client = _StubLLMClient("not json", mocked=True)
    captured: list[list[LLMMessage]] = []

    def capture(messages: list[LLMMessage]) -> LLMCompletion:
        captured.append(messages)
        return LLMCompletion(content="not json", model="stub", mocked=True)

    client.complete = capture  # type: ignore[method-assign]
    EvidenceAgent(client).extract(
        mission_id=uuid4(), source_id=uuid4(), source=_source(), mission_goal=GOAL
    )

    user_message = captured[0][-1].content
    assert GOAL in user_message
    # The goal must sit outside the untrusted source block.
    assert user_message.index(GOAL) < user_message.index("<source_data>")
