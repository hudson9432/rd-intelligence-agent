"""Phase C analysis wired as a workflow stage.

Composes the Analyst, the Critic, and the viability gate into the single
`analyze` call the orchestrator's `AnalysisStage` protocol expects, so the
workflow's Analysis node runs the real thing rather than a placeholder.

`docs/PHASE_C_CONTRACT.md` splits ownership: C decides the *content* of
targeted re-search and owns the viability gate, while D owns loop execution and
iteration limits. That boundary is preserved here — this stage passes
`research_exhausted` through and returns the handoff untouched; it never
decides whether to search again.

The generation boundaries C declares are satisfied by `LLMAnalysisAdapter`,
which runs on B's provider-independent client. With `MOCK_LLM=true` the adapter
takes its deterministic paths, so the stage makes no external call.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.agents.analysis_llm import AnalysisGenerationError, LLMAnalysisAdapter
from app.agents.analyst import AnalystAgent
from app.agents.critic import CriticAgent
from app.agents.orchestrator import WorkflowStageError
from app.core.config import Settings, get_settings
from app.core.llm import LLMClient, get_llm_client
from app.schemas.analysis import ClaimReview, PhaseCHandoff
from app.schemas.evidence_card import EvidenceCard
from app.services.phase_c import build_phase_c_handoff


class PhaseCAnalysisStage:
    """Runs Analyst, Critic, and the Phase C gate as one workflow stage."""

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        *,
        settings: Settings | None = None,
        max_active_directions: int = 4,
        minimum_question_score: float = 0.6,
    ) -> None:
        client = llm_client or get_llm_client(settings or get_settings())
        adapter = LLMAnalysisAdapter(client)
        self._adapter = adapter
        self._analyst = AnalystAgent(
            adapter, max_active_directions=max_active_directions
        )
        self._critic = CriticAgent(adapter, adapter, minimum_score=minimum_question_score)

    def analyze(
        self,
        *,
        mission_goal: str,
        evidence: Sequence[EvidenceCard],
        research_exhausted: bool,
    ) -> PhaseCHandoff:
        try:
            analysis = self._analyst.analyze(
                mission_goal=mission_goal, evidence=evidence
            )
            critique = self._critic.critique(
                mission_goal=mission_goal, analysis=analysis, evidence=evidence
            )
            # Claim review is only meaningful once directions exist; asking for
            # it on a research-required analysis would spend a call on nothing.
            claim_reviews: Sequence[ClaimReview] = (
                self._adapter.review_claims(
                    analysis=analysis, critique=critique, evidence=evidence
                )
                if analysis.status == "ready"
                else []
            )
            return build_phase_c_handoff(
                mission_goal=mission_goal,
                analysis=analysis,
                critique=critique,
                evidence=evidence,
                claim_reviews=claim_reviews,
                research_exhausted=research_exhausted,
            )
        except AnalysisGenerationError as error:
            # A provider that returns an uninterpretable response is a failure,
            # not a reason to guess: invariant 1 forbids inventing the analysis.
            raise WorkflowStageError(
                f"The analysis provider returned an unusable response: {error}"
            ) from error
