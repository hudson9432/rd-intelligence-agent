# B–C integration boundary

This integration keeps Evidence extraction and Analysis independently
replaceable while preserving stable provenance.

## Data handoff

    B EvidenceAgent
      -> EvidenceCardCreate
      -> persist_evidence_for_analysis
      -> repository assigns stable evidence ID
      -> EvidenceCard
      -> C AnalystAgent

C never accepts an unpersisted EvidenceCardCreate as recommendation evidence.
The bridge validates that the batch belongs to one mission and that persistence
does not change mission or source provenance.

## LLM handoff

LLMAnalysisAdapter uses B's provider-independent LLMClient and implements C's
direction generator, critique-question generator, independent question review,
and claim review interfaces. Real provider responses must satisfy strict
Pydantic JSON contracts. Malformed responses become AnalysisGenerationError
rather than partial or guessed analysis.

The same adapter supports MockLLMClient without external calls. Mock directions
and questions are derived only from persisted EvidenceCard fields and IDs.

## Requested B-side follow-up

No B-owned behavior is changed by this integration branch. The following
adjustments are recommended to the B owner:

1. The current generic mock Evidence extraction assigns relevance_score zero.
   That is safe, but C must then reject every resulting direction for zero
   evidence coverage. For the deterministic demo, prefer a fixture-driven
   structured mock response with explicit relevance and confidence values.
2. Do not make generic mock extraction guess relevance from source text because
   EvidenceAgent currently does not receive the mission goal. Relevance cannot
   be judged honestly without that context.
3. Consider adding a typed structured-completion helper to LLMClient later.
   LLMAnalysisAdapter currently performs strict Pydantic parsing locally to
   avoid changing B's public provider contract during parallel work.
4. Continue returning EvidenceCardCreate from extraction. Stable evidence IDs
   must come from persistence, not from the LLM or Evidence Agent.

These are integration recommendations, not requirements for merging this
branch. The interface works with the current B contracts.
