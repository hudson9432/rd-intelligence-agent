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

- diversity: deterministic character-bigram distance from accepted questions;
- rationality: supplied by an independent semantic reviewer;
- viewpoint_coverage: supplied by the reviewer and measures whether the
  question plus cited evidence materially cover the challenged claim.

Rejected questions do not consume an accepted slot. If no question survives,
the Critic creates a bounded research request from the least-supported claims.
Accepted questions with suggested searches also produce a targeted request of
at most three queries.

## Handoff to D

PhaseCHandoff.status is exactly one of:

- ready_for_poc: one or more evidence-grounded PocCandidate values are
  available. A candidate is a direction and validation hypothesis, not an
  executable action plan; D owns task planning.
- research_required: C supplies a TargetedResearchRequest; D invokes the
  source tools and reruns C while enforcing the workflow iteration limit.
- no_viable_direction: material gaps remain after D reports that the research
  budget is exhausted. No PoC candidate is emitted.

C therefore owns the content of targeted re-search and the viability gate. D
owns loop execution, iteration limits, persistence, events, and conversion of a
PoC candidate into an ActionPlan.

## Integration boundaries

The Phase C implementation deliberately does not modify shared schema exports,
configuration, API routers, database models, repositories, or requirements.
LLM and mock implementations integrate through the DirectionGenerator,
CritiqueQuestionGenerator, and QuestionReviewer protocols.
