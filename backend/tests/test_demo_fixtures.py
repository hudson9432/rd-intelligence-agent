"""The committed demo fixtures must carry the offline scenario end to end.

These assert on the fixtures themselves, so a refresh through
`demo/capture_fixtures.py` that quietly breaks the demo fails here rather than
during a live run.
"""

from datetime import UTC, datetime
from uuid import uuid4

from app.agents.evidence import EvidenceAgent
from app.core.config import Settings
from app.core.llm import MockLLMClient
from app.schemas.evidence_card import EvidenceCard
from app.services.analysis_stage import PhaseCAnalysisStage
from app.services.research_source import ResearchSourceService

GOAL = (
    "Decide whether retrieval augmented generation is reliable enough for our product."
)


def mock_settings() -> Settings:
    return Settings(mock_external_apis=True, demo_mode=False)


async def fixture_evidence() -> list[EvidenceCard]:
    """Replay the fixtures through real extraction, as a live run would."""

    response = await ResearchSourceService(settings=mock_settings()).search(
        GOAL, max_results_per_source=8
    )
    agent = EvidenceAgent(MockLLMClient())
    cards: list[EvidenceCard] = []
    mission_id = uuid4()
    for source in response.results:
        created = agent.extract(
            mission_id=mission_id,
            source_id=uuid4(),
            source=source,
            mission_goal=GOAL,
        )
        cards.append(
            EvidenceCard(
                id=uuid4(), created_at=datetime.now(UTC), **created.model_dump()
            )
        )
    return cards


async def test_the_fixtures_yield_both_sources_and_no_errors() -> None:
    response = await ResearchSourceService(settings=mock_settings()).search(
        GOAL, max_results_per_source=8
    )

    assert response.errors == []
    assert {result.source_type for result in response.results} == {"arxiv", "github"}


async def test_most_fixture_sources_score_above_zero_relevance() -> None:
    """A refresh whose sources are unrelated to the demo goal is unusable.

    Not every source: `goal_overlap` is lexical, so a source that discusses the
    goal in other words — "RAG" for "retrieval augmented generation" — scores
    zero even though a real provider would rate it highly. That false negative
    is a documented property of offline mode, not a fixture problem.
    """

    cards = await fixture_evidence()
    scored = [card for card in cards if card.relevance_score > 0]

    assert cards
    assert len(scored) > len(cards) // 2, (
        "Most fixture sources score zero against the demo goal; refresh them "
        "with a query closer to it. See demo/capture_fixtures.py."
    )


async def test_most_fixture_sources_state_a_limitation() -> None:
    """The Critic can only stop asking for research once evidence has caveats.

    A refreshed fixture set whose abstracts state no limitation cannot reach a
    PoC candidate however well the agents work, so it is caught here.
    """

    cards = await fixture_evidence()
    with_limitation = [card for card in cards if card.limitation]

    assert len(with_limitation) >= len(cards) // 2, (
        "Refresh the fixtures with a query whose abstracts discuss caveats; "
        "see demo/capture_fixtures.py."
    )


async def test_the_offline_demo_reaches_a_poc_candidate() -> None:
    cards = await fixture_evidence()

    handoff = PhaseCAnalysisStage(MockLLMClient()).analyze(
        mission_goal=GOAL, evidence=cards, research_exhausted=False
    )

    assert handoff.status == "ready_for_poc", handoff.reason
    assert handoff.poc_candidates
    supplied = {card.id for card in cards}
    for candidate in handoff.poc_candidates:
        assert set(candidate.evidence_ids) <= supplied


async def test_the_offline_demo_is_deterministic() -> None:
    first = PhaseCAnalysisStage(MockLLMClient()).analyze(
        mission_goal=GOAL, evidence=await fixture_evidence(), research_exhausted=False
    )
    second = PhaseCAnalysisStage(MockLLMClient()).analyze(
        mission_goal=GOAL, evidence=await fixture_evidence(), research_exhausted=False
    )

    assert first.status == second.status
    assert len(first.poc_candidates) == len(second.poc_candidates)
