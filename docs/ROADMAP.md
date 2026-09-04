# Implementation roadmap

Status values: `complete`, `in progress`, `next`, `planned`, `optional`.

| Phase | Status | Deliverable |
| --- | --- | --- |
| 01 | complete | Repository, FastAPI health API, schemas, Next.js shell, tests |
| 02 | complete | SQLite persistence, repositories, mission/event APIs |
| 03 | complete | arXiv and GitHub tools, normalization, deduplication, mock sources |
| 04 | in progress | Provider-independent LLM client and deterministic mock LLM |
| 05 | planned | Search Agent |
| 06 | in progress | Evidence Agent with strict provenance |
| 07 | planned | Analyst Agent and deterministic opportunity scoring |
| 08 | planned | Critic Agent, coverage scoring, targeted query output |
| 09 | in progress | LangGraph orchestrator and bounded re-search routing |
| 10 | planned | Decision Engine |
| 11 | planned | Action Agent and PoC task plan |
| 12 | optional | User-approved calendar proposal/execution integration |
| 13 | planned | Mission, evidence, decision, and action frontend views |
| 14 | planned | Deterministic offline Demo Mode |
| 15 | planned | Comprehensive unit, agent, API, and workflow tests |
| 16 | planned | Engineering audit and focused refactor |
| 17 | planned | Hackathon submission README and demo links |
| 18 | planned | Reviewer audit, live-demo hardening, final checklist |

Each phase should land as a scoped issue/PR and leave the repository passing
backend tests plus frontend lint/build.

Phases 04 and 06 have foundational components landing early to unblock parallel
work. They remain in progress until structured generation/mock fixtures and the
full deduplicate-filter-persist-event Evidence pipeline are complete.

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

Phase 14 has a hard prerequisite: the fixtures in `demo/fixtures/` are
one-sentence blurbs with no stated limitations, and offline extraction quotes a
limitation only when the source states one. Without richer fixtures the demo
stops at `research_required` however well the agents work. Capture them from
the live APIs; do not hand-write abstracts for real papers.
