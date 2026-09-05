# Phase C — Analysis and Critic contract

Phase C is isolated from source retrieval, persistence, API routing, and PoC
task planning. It accepts a mission goal plus evidence cards and produces one
of three typed handoffs for the orchestration owner.

## Flow

    Evidence cards
      -> propose evidence-grounded directions
      -> rank by evidence coverage
      -> activate 1–4 directions and retain the rest as candidates
      -> generate adversarial questions and replacement candidates
      -> independently review diversity, rationality, and viewpoint coverage
      -> emit targeted research, PoC candidates, or no viable direction

Unknown support is scored as zero coverage, not as counter-evidence. Every
cited evidence ID must occur in the supplied evidence set, and all supplied
evidence must belong to one mission.

## Evidence sufficiency entry gate

Before asking the Analyst to generate directions, deterministic code checks
whether the pool contains at least two effective cards from at least two
independent source IDs. An effective card must have relevance of at least 0.2
and extraction confidence of at least 0.6. Raw result count therefore cannot
be used to fill the pool with weak cards.
Only cards that pass both thresholds enter Analyst, Critic, claim review, and
the viability gate; an excluded card cannot later support or oppose a claim.

The handoff carries an `EvidenceSufficiencyReport` containing every evidence
ID, its relevance-confidence quality score, its eligibility or exclusion
reason, independent-source count, and counts of result- and limitation-bearing
cards. Result and limitation counts are visible diagnostics rather than global
hard gates because a non-experimental strategy source can still be relevant.
Claim-specific support, counterevidence, and testability remain the later
viability gate's responsibility.

If the entry gate fails while research budget remains, C returns a bounded
targeted research request without spending Analyst/Critic model calls. If the
budget is exhausted, it returns `no_viable_direction`; low-quality or
single-source evidence cannot become viable merely because search stopped.

## Analyst output

AnalystOutcome has two states:

- ready: contains one to four active directions. Extra valid directions stay
  in candidate_directions and are never silently deleted.
- research_required: no direction has traceable supporting evidence.

Each direction contains testable claims and exact supporting evidence IDs.
Evidence coverage is calculated in code from relevance, extraction confidence,
and bounded independent-source corroboration. It is not supplied by the
direction generator.

## Critic output

The question generator supplies more candidate questions than the result needs.
Candidates are processed as a replacement queue. A question is rejected if any
of these scores is below the configured threshold:

- diversity: deterministic character-bigram distance from accepted questions
  for the same direction (questions for different directions do not compete);
- rationality: supplied by an independent semantic reviewer;
- viewpoint_coverage: supplied by the reviewer and measures whether the
  question plus cited evidence materially cover the challenged claim.

Rejected questions do not consume an accepted slot. If no question survives,
the Critic creates a bounded research request from the least-supported claims.
Accepted questions with suggested searches also produce a targeted request of
at most three queries.

## Pro/con claim verdicts

After targeted evidence is available, an independent reviewer identifies
opposing evidence IDs and scores whether each claim can be tested by a bounded
PoC. Code calculates support and counterevidence strength from the cited
evidence cards. Missing review or missing evidence remains unknown and is never
converted into negative evidence.

A review that cannot be applied counts as missing. Every generator here is a
language model, and a model can cite an identifier that does not exist,
contradict itself by opposing the evidence it also cites as support, review a
claim that is not under analysis, or return two reviews for one claim. Such a
review is discarded and its claim is judged as if no review arrived. The same
rule governs the Analyst and the Critic: a direction or question that cites
evidence outside the supplied set is dropped, and the remaining ones are kept.
Rejecting the invented reference is required by invariant 2; rejecting
everything alongside it is not, and discards work that is sound.

Each claim receives one of four verdicts:

- supported: meaningful support with weak counterevidence;
- contested: meaningful evidence exists on both sides;
- unknown: support or independent review is insufficient;
- refuted: strong counterevidence exceeds support by a material margin.

A direction is PoC-ready only when it has at least one minimally supported and
testable core hypothesis, no core claim is refuted, and every unresolved core
claim can be tested within the PoC. A contested direction may therefore remain
PoC-ready: the purpose of its PoC is to resolve the uncertainty.

## Handoff to D

PhaseCHandoff.status is exactly one of:

- ready_for_poc: one or more evidence-grounded PocCandidate values are
  available. A candidate is a direction and validation hypothesis, not an
  executable action plan; D owns task planning.
- research_required: C supplies a TargetedResearchRequest; D invokes the
  source tools and reruns C while enforcing the workflow iteration limit.
- no_viable_direction: material gaps remain after D reports that the research
  budget is exhausted and no direction satisfies the core-claim viability
  rules. No PoC candidate is emitted. Missing evidence never causes this state
  before the bounded re-search opportunity has been used.

Outstanding critique questions request research only while budget remains. Once
D reports the budget exhausted, they stop deciding the outcome and the claim
verdicts do: a critic can always ask another question, and that is not the same
as no direction being viable. Any question left unanswered travels into the PoC
candidate as an unresolved question, which is what a PoC is for.

C therefore owns identification of targeted evidence gaps and the viability
gate. The Search Agent converts those gaps and suggested searches into final,
history-aware queries. D owns loop execution, iteration limits, persistence,
events, and conversion of a PoC candidate into an ActionPlan.

## Integration boundaries

The Phase C implementation deliberately does not modify shared schema exports,
configuration, API routers, database models, repositories, or requirements.
LLM and mock implementations integrate through the DirectionGenerator,
CritiqueQuestionGenerator, QuestionReviewer, and ClaimReview contracts.
