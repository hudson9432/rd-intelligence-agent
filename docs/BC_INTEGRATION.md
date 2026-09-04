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

## B-side follow-up

Items 1 and 2 are addressed; 3 and 4 remain open.

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
3. **Open.** Consider adding a typed structured-completion helper to LLMClient.
   LLMAnalysisAdapter performs strict Pydantic parsing locally to avoid
   changing B's public provider contract during parallel work.
4. **Held.** Extraction still returns EvidenceCardCreate; stable evidence IDs
   still come from persistence.

## Known gap: demo fixtures

Mock extraction quotes a limitation only when the source states one, because
inventing a caveat would breach invariant 1. The mock critique-question
generator, in turn, only produces a question without a suggested search when
the evidence card records a limitation — so a source that states no caveat can
never reach a PoC candidate offline.

The fixtures in `demo/fixtures/` are one-sentence blurbs for real papers and
repositories, with no stated limitations, so the current demo path stops at
`research_required`. The chain is proven to work on sources that do state
caveats (`test_extracted_evidence_reaches_a_poc_candidate_offline`); what is
missing is fixture content, not capability.

Phase 14 should capture fuller responses from the live arXiv and GitHub APIs
rather than hand-writing abstracts for real papers, which would fabricate
source text.
