# Implementation roadmap

Status values: `complete`, `in progress`, `next`, `planned`, `optional`.

| Phase | Status | Deliverable |
| --- | --- | --- |
| 01 | complete | Repository, FastAPI health API, schemas, Next.js shell, tests |
| 02 | complete | SQLite persistence, repositories, mission/event APIs |
| 03 | complete | arXiv and GitHub tools, normalization, deduplication, mock sources |
| 04 | in progress | Provider-independent LLM client and deterministic mock LLM |
| 05 | in progress | Search Agent |
| 06 | in progress | Evidence Agent with strict provenance |
| 07 | complete | Analyst Agent and deterministic opportunity scoring |
| 08 | complete | Critic Agent, coverage scoring, targeted query output |
| 09 | in progress | LangGraph orchestrator and bounded re-search routing |
| 10 | planned | Decision Engine |
| 11 | planned | Action Agent and PoC task plan |
| 12 | optional | User-approved calendar proposal/execution integration |
| 13 | in progress | Mission, evidence, decision, and action frontend views |
| 14 | planned | Deterministic offline Demo Mode |
| 15 | planned | Comprehensive unit, agent, API, and workflow tests |
| 16 | planned | Engineering audit and focused refactor |
| 17 | planned | Hackathon submission README and demo links |
| 18 | planned | Reviewer audit, live-demo hardening, final checklist |

Each phase should land as a scoped issue/PR and leave the repository passing
backend tests plus frontend lint/build.

Phase 04 remains in progress until `LLMClient` offers a typed
structured-completion helper; every caller currently repeats strict Pydantic
parsing of its own.

Phase 05 is in progress rather than complete: `ResearchSourceSearchStage`
executes the mission's queries, merges, and drops sources already seen, but it
authors no queries. Round one searches the goal and later rounds search what
the Critic asked for, which `docs/PHASE_C_CONTRACT.md` assigns to Phase C.
Whether a separate query-authoring agent is still wanted is an open question.

Phase 06 now deduplicates, filters, and persists: `PersistingEvidenceStage`
stores each source, extracts against the mission goal, skips sources that fail
their provenance checks, and persists evidence through the B-to-C bridge so
ids come from the database. It remains in progress until the demo relies on
something better than lexical relevance scoring offline.

Phases 07 and 08 landed with the Analyst, Critic, coverage scoring, and
targeted query output, recorded in `docs/PHASE_C_CONTRACT.md`. The table said
`planned` for longer than it should have.

A mission now runs end to end offline: goal to sources to persisted evidence to
a Phase C handoff to a decision. It stops short of an action plan because
phase 11 is not built.

Phase 09 has landed as a graph skeleton: routing, the bounded re-search loop,
event persistence, and mission status are implemented and tested. Its Analysis
stage is real; Search, Evidence, Decision, and Action are still placeholders.
It remains in progress until real stages replace them.

Phase 07/08 analysis is reachable from the workflow: `PhaseCAnalysisStage`
composes the Analyst, the Critic, and the viability gate behind the graph's
Analysis node. On the deterministic mock provider the pipeline produces a real,
evidence-grounded PoC candidate when it is given evidence that records
limitations. It cannot do so from a live mission yet, because the Search and
Evidence stages that would supply that evidence are not built.

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

What phase 14 still needs is a query-aware mock: replay ignores the query, so a
targeted re-search round returns the same sources it already has and the
bounded loop cannot improve its evidence offline. Until per-query fixture sets
exist, the Critic-driven re-search loop — the product's stated differentiator —
is not observable in mock mode.
