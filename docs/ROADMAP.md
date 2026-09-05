# Implementation roadmap

Status values: `complete`, `in progress`, `next`, `planned`, `optional`.

| Phase | Status | Deliverable |
| --- | --- | --- |
| 01 | complete | Repository, FastAPI health API, schemas, Next.js shell, tests |
| 02 | complete | SQLite persistence, repositories, mission/event APIs |
| 03 | complete | arXiv and GitHub tools, normalization, deduplication, mock sources |
| 04 | complete | Provider-independent LLM client and deterministic mock LLM |
| 05 | complete | Search Agent |
| 06 | in progress | Evidence Agent with strict provenance |
| 07 | complete | Analyst Agent and deterministic opportunity scoring |
| 08 | complete | Critic Agent, coverage scoring, targeted query output |
| 09 | in progress | LangGraph orchestrator and bounded re-search routing |
| 10 | complete | Decision Engine |
| 11 | complete | Action Agent and PoC task plan |
| 12 | optional | User-approved calendar proposal/execution integration |
| 13 | in progress | Mission, evidence, decision, and action frontend views |
| 14 | planned | Deterministic offline Demo Mode |
| 15 | planned | Comprehensive unit, agent, API, and workflow tests |
| 16 | planned | Engineering audit and focused refactor |
| 17 | planned | Hackathon submission README and demo links |
| 18 | planned | Reviewer audit, live-demo hardening, final checklist |

Each phase should land as a scoped issue/PR and leave the repository passing
backend tests plus frontend lint/build.

Phase 04 includes a typed structured-completion helper. OpenAI-compatible
structured calls request JSON object mode, tolerate one Markdown JSON fence,
and validate against the caller's Pydantic contract. Schema and provider errors
terminate the relevant workflow stage instead of being interpreted as missing
research evidence. Configurable process-wide pacing lets every agent sharing a
provider/model respect low requests-per-minute tiers.

Phase 05 now has a typed Search Agent. It uses the configured LLM only to plan
at most four focused queries, applies deterministic normalization and exact
history deduplication, and then delegates retrieval to the existing arXiv and
GitHub tools. First-pass planning covers research, implementations, benchmarks,
and adoption; later rounds turn Critic-supplied evidence gaps into targeted
queries. Generated queries and notes are persisted through AgentEvents, while
the workflow result retains the bounded query history.

Phase 06 now deduplicates, filters, and persists: `PersistingEvidenceStage`
stores each source, extracts against the mission goal, skips sources that fail
their provenance checks, and persists evidence through the B-to-C bridge so
ids come from the database. It remains in progress until the demo relies on
something better than lexical relevance scoring offline. Live-model provenance
tolerates Unicode and whitespace normalization but still rejects paraphrased or
invented quotes; if every new source is rejected, the workflow fails explicitly.

Phases 07 and 08 landed with the Analyst, Critic, coverage scoring, and
targeted query output, recorded in `docs/PHASE_C_CONTRACT.md`. The table said
`planned` for longer than it should have.

Phase 10 scores every candidate on six dimensions and recommends the highest.
Four are rated by a model against the supplied evidence, each anchored so a
score means the same thing every time — `technical_maturity` follows the NASA
technology readiness scale, and `novelty` is explicitly rarity *within the
supplied evidence* rather than in the world. The other two are derived in code
from what Phase C established, and the combining formula is code as well.

The formula's shape is borrowed: RICE supplies the point that confidence
multiplies and effort divides, and the benefit/readiness/cost grouping follows
stage-gate scorecards. The weighting inside each group is flat, because there
is no evidence that novelty should outrank goal alignment and a precise weight
vector would manufacture the false precision the scoring exists to avoid. Read
the score as merit per unit of difficulty and beside the six dimensions, not
instead of them.

It also closes a gap nothing else covered: `goal_alignment` is the only place
that asks whether a direction answers the mission's question. The Analyst ranks
on evidence coverage and breaks ties on title, so a well-evidenced but
tangential direction otherwise wins by default. The field replaced
`business_impact`, which no available data could ground.

Every scored candidate is stored, not only the winner, because a reader who
cannot see what the alternatives scored has no way to disagree.

Phase 11 turns the selected PoC candidate into a task plan. Every task must
name an open item the candidate carries — an unsettled claim or a reviewer
question — and a task naming nothing is discarded, so a plan cannot be a
generic checklist that fits any mission. Identifiers, dependency resolution,
effort aggregation, and the task ceiling are decided in code; the model writes
only the work. A task may depend only on an earlier task, which makes a cycle
unrepresentable rather than something to detect.

A mission now runs end to end offline: goal to sources to persisted evidence to
a Phase C handoff to a decision to a stored action plan. Only the Decision
stage is still provisional.

The backend prerequisite for Phase 13 is available through
`GET /missions/{id}/result`. It aggregates provenance, evidence eligibility and
audit findings, Phase C claim verdicts, every scored opportunity, the decision,
and the stored action plan. Phase 13 remains in progress until the frontend
renders that contract and polls workflow events.

Real-provider runs can be queued through `POST /missions/{id}/run/async` and
observed through mission status plus persisted events. This in-process runner
prevents a chain of model calls from holding open the initiating request, but a
durable external job queue remains production work.

Phase 09 has landed as a graph skeleton: routing, the bounded re-search loop,
event persistence, and mission status are implemented and tested. Search,
Evidence, and Analysis use their real implementations; Decision is provisional
and Action remains a placeholder. It remains in progress until those final
stages are real and background execution is durable.

Phase 07/08 analysis is reachable from the workflow: `PhaseCAnalysisStage`
composes the Analyst, the Critic, and the viability gate behind the graph's
Analysis node. On the deterministic mock provider the pipeline produces a real,
evidence-grounded PoC candidate when it is given evidence that records
limitations. A configured real provider now drives all four Phase C generation
and review boundaries through the same structured-output contract.

The graph runs on LangGraph (`langgraph==1.2.11`). This is a deliberate,
recorded exception to the `AGENTS.md` rule against adding a framework while a
small abstraction would do: the workflow is the product's core loop, and
LangGraph's checkpointing, streaming, and concurrent fan-out are expected to be
needed as real stages land.

The other `AGENTS.md` rules still bind. Routing and the re-search bound stay in
deterministic Python: routers are pure functions of state, the iteration limit
is enforced inside the analysis node, and LangGraph's `recursion_limit` is only
a backstop against a routing bug. Nodes sequence work and emit events; no
scoring, parsing, or business rule lives in one.

Phase 14's fixture prerequisite is met. `demo/capture_fixtures.py` captures
real arXiv and GitHub responses, and the committed set now reaches
`ready_for_poc` deterministically offline, guarded by
`backend/tests/test_demo_fixtures.py`. Refresh fixtures with that script; do
not hand-write abstracts for real papers.

Phase 14 now has a bounded query-aware RAG mock profile. General queries replay
the baseline sources, while citation, hallucination, prompt-injection, Ragas,
and failure-benchmark follow-ups replay a distinct raw arXiv capture. Tests
verify that a targeted second round adds new source URLs. Broader topic-specific
fixture profiles and a polished scripted demo remain optional extensions.
