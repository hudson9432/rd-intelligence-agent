"""A fixed pro/con e-commerce scenario from captured real arXiv sources."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from app.agents.action import ActionAgent
from app.core.llm import MockLLMClient
from app.schemas.analysis import (
    AnalystOutcome,
    ClaimReview,
    CriticOutcome,
    CritiqueQuestionDraft,
    DirectionClaim,
    EvaluatedCritiqueQuestion,
    QuestionScores,
    RankedDirection,
)
from app.schemas.evidence_card import EvidenceCard
from app.schemas.source_result import SourceResult
from app.schemas.workflow import WorkflowDecision
from app.services.phase_c import build_phase_c_handoff
from app.tools.arxiv import parse_feed

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = (
    ROOT / "demo" / "fixtures" / "ecommerce_recommender_pro_con_arxiv_response.xml"
)
SCENARIO = ROOT / "demo" / "fixtures" / "ecommerce_recommender_scenario.json"
MISSION_ID = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")


def load_scenario() -> tuple[dict[str, Any], dict[str, SourceResult]]:
    scenario = json.loads(SCENARIO.read_text(encoding="utf-8"))
    sources = parse_feed(FIXTURE.read_text(encoding="utf-8"))
    by_arxiv_id = {
        item["arxiv_id"]: next(
            source for source in sources if item["arxiv_id"] in source.url
        )
        for item in scenario["sources"]
    }
    return scenario, by_arxiv_id


def evidence_card(source: SourceResult) -> EvidenceCard:
    """Copy the captured abstract into evidence without composing a finding."""

    assert source.summary is not None
    return EvidenceCard(
        id=uuid5(NAMESPACE_URL, f"evidence:{source.url}"),
        mission_id=MISSION_ID,
        source_id=uuid5(NAMESPACE_URL, f"source:{source.url}"),
        result=source.summary,
        evidence_snippets_json=[source.summary],
        relevance_score=0.9,
        extraction_confidence=0.9,
        created_at=datetime.now(UTC),
    )


def test_ecommerce_fixture_contains_quantified_support_and_challenges() -> None:
    scenario, sources = load_scenario()
    roles = {
        role: [
            sources[item["arxiv_id"]]
            for item in scenario["sources"]
            if item["role"] == role
        ]
        for role in ("support", "challenge")
    }
    support_text = " ".join(source.summary or "" for source in roles["support"])
    challenge_text = " ".join(source.summary or "" for source in roles["challenge"])

    assert len(sources) == 4
    assert {item["role"] for item in scenario["sources"]} == {
        "support",
        "challenge",
    }
    assert "2.48%" in support_text and "7.34%" in support_text
    assert "+0.25%" in support_text
    assert "11 out of the 12" in challenge_text
    assert "popularity bias" in challenge_text


def test_contested_ecommerce_claim_maps_every_question_to_an_action_task() -> None:
    scenario, sources = load_scenario()
    cards = {arxiv_id: evidence_card(source) for arxiv_id, source in sources.items()}
    support_ids = [
        cards[item["arxiv_id"]].id
        for item in scenario["sources"]
        if item["role"] == "support"
    ]
    challenge_ids = [
        cards[item["arxiv_id"]].id
        for item in scenario["sources"]
        if item["role"] == "challenge"
    ]
    direction = RankedDirection(
        id=scenario["direction_id"],
        title=scenario["direction_title"],
        summary=scenario["claim"],
        claims=[
            DirectionClaim(
                id=scenario["claim_id"],
                statement=scenario["claim"],
                evidence_ids=support_ids,
            )
        ],
        evidence_coverage=0.91,
        rank=1,
    )
    analysis = AnalystOutcome(status="ready", active_directions=[direction])
    questions = [
        EvaluatedCritiqueQuestion(
            question=CritiqueQuestionDraft(
                id=item["id"],
                direction_id=direction.id,
                challenged_claim_id=scenario["claim_id"],
                question=item["question"],
                rationale="The captured challenge source exposes this risk.",
                evidence_ids=[
                    cards[source_id].id for source_id in item["source_arxiv_ids"]
                ],
            ),
            scores=QuestionScores(
                diversity=0.9,
                rationality=0.9,
                viewpoint_coverage=0.9,
            ),
        )
        for item in scenario["important_questions"]
    ]
    critique = CriticOutcome(status="ready", accepted_questions=questions)

    handoff = build_phase_c_handoff(
        mission_goal=scenario["mission_goal"],
        analysis=analysis,
        critique=critique,
        evidence=list(cards.values()),
        claim_reviews=[
            ClaimReview(
                direction_id=direction.id,
                claim_id=scenario["claim_id"],
                opposing_evidence_ids=challenge_ids,
                poc_testability=0.9,
                rationale=(
                    "The observed gains and documented trade-offs can be compared "
                    "in a bounded controlled experiment."
                ),
            )
        ],
        research_exhausted=True,
    )

    assert handoff.status == "ready_for_poc"
    contested = [
        claim for claim in handoff.claim_assessments if claim.verdict == "contested"
    ]
    assert contested
    assert contested[0].supporting_evidence_ids == support_ids
    assert contested[0].opposing_evidence_ids == challenge_ids

    candidate = handoff.poc_candidates[0]
    plan = ActionAgent(MockLLMClient()).plan(
        mission_id=MISSION_ID,
        mission_goal=scenario["mission_goal"],
        candidate=candidate,
        decision=WorkflowDecision(
            recommendation="proceed_with_poc",
            selected_direction_id=direction.id,
            rationale="The contested claim is measurable in a PoC.",
        ),
    )

    expected_question_ids = {
        f"question-{index}"
        for index in range(1, len(scenario["important_questions"]) + 1)
    }
    mapped_question_ids = {
        task.addresses
        for task in plan.tasks_json
        if task.addresses.startswith("question-")
    }
    assert mapped_question_ids == expected_question_ids
