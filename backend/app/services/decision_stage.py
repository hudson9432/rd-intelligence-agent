"""Opportunity scoring wired as a workflow stage.

Phase 10. Scores every candidate Phase C put forward, stores the scores, and
recommends one.

The scores are persisted because they are the reason for the recommendation. A
reader who can see only the winner has no way to disagree; one who can see what
the alternatives scored, and on which dimension they lost, does.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.orm import Session

from app.agents.decision import DecisionAgent, DecisionScoringError, recommend
from app.agents.orchestrator import WorkflowStageError
from app.core.config import Settings, get_settings
from app.core.llm import LLMClient, LLMProviderError, get_llm_client
from app.repositories.technology_opportunity import TechnologyOpportunityRepository
from app.schemas.analysis import PhaseCHandoff
from app.schemas.evidence_card import EvidenceCard
from app.schemas.workflow import WorkflowDecision


class OpportunityDecisionStage:
    """Scores the candidates, records them, and recommends the best."""

    def __init__(
        self,
        session: Session,
        llm_client: LLMClient | None = None,
        *,
        settings: Settings | None = None,
    ) -> None:
        self._opportunities = TechnologyOpportunityRepository(session)
        self._agent = DecisionAgent(
            llm_client or get_llm_client(settings or get_settings())
        )

    def decide(
        self,
        *,
        mission_goal: str,
        handoff: PhaseCHandoff,
        evidence: Sequence[EvidenceCard],
    ) -> WorkflowDecision:
        if not handoff.poc_candidates:
            return WorkflowDecision(
                recommendation="do_not_proceed",
                rationale=f"Phase C reported {handoff.status}. {handoff.reason}",
            )

        mission_id = _mission_of(evidence)
        try:
            scored = self._agent.score(
                mission_id=mission_id,
                mission_goal=mission_goal,
                handoff=handoff,
                evidence=evidence,
            )
        except LLMProviderError as error:
            raise WorkflowStageError(
                "The decision provider request failed; nothing was scored."
            ) from error
        except DecisionScoringError as error:
            raise WorkflowStageError(
                f"The decision provider returned unusable ratings: {error}"
            ) from error

        self._opportunities.replace_for_mission(
            mission_id, [item.opportunity for item in scored]
        )
        return recommend(scored)


def _mission_of(evidence: Sequence[EvidenceCard]) -> UUID:
    """Every card in a run belongs to one mission; the gate already checks it."""

    if not evidence:
        raise WorkflowStageError(
            "Scoring needs evidence to attribute the opportunity to a mission."
        )
    return evidence[0].mission_id
