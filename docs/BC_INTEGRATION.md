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
and claim review interfaces. All four use `LLMClient.complete_structured`, which
requests JSON object mode from OpenAI-compatible providers, removes one optional
Markdown JSON fence, and validates the Pydantic contract. Malformed responses
become `AnalysisGenerationError` rather than partial or guessed analysis.

The same adapter supports MockLLMClient without external calls. Mock directions
and questions are derived only from persisted EvidenceCard fields and IDs.

## B-side follow-up

Items 1–3 are addressed; item 4 remains held by design.

1. **Done.** Generic mock extraction no longer assigns relevance_score zero, so
   directions no longer fail Phase C on zero evidence coverage. The score comes
   from `goal_overlap`, a deterministic lexical-containment signal.
2. **Done, by removing the reason it could not be judged.** EvidenceAgent now
   takes `mission_goal`, so relevance has something to be relative to. The
   prompt carries the goal as well, which matters beyond mock mode: a real
   provider was previously asked for a relevance score without being told what
   the mission was trying to decide. The mock still does not guess — overlap is
   lexical, and it is documented as a stand-in for a model's judgement rather
   than a semantic measure.
3. **Done.** `LLMClient.complete_structured` is the shared typed boundary for
   Evidence and every Phase C generation/review call. Deterministic mock
   factories remain explicit at the call site.
4. **Held.** Extraction still returns EvidenceCardCreate; stable evidence IDs
   still come from persistence.

## Known gap: demo fixtures

Mock extraction quotes a limitation only when the source states one, because
inventing a caveat would breach invariant 1. The mock critique-question
generator, in turn, only produces a question without a suggested search when
the evidence card records a limitation — so a source that states no caveat can
never reach a PoC candidate offline.

The fixtures in `demo/fixtures/` are frozen responses captured from the live
arXiv and GitHub APIs. The current set contains stated limitations and reaches
`ready_for_poc` deterministically. Mock replay remains query-insensitive, so a
targeted re-search round cannot demonstrate improvement from new evidence yet.
