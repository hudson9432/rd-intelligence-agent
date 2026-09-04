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
| 09 | planned | LangGraph orchestrator and bounded re-search routing |
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

Phases 04 and 06 have foundational components landing early to unblock parallel
work. They remain in progress until structured generation/mock fixtures and the
full deduplicate-filter-persist-event Evidence pipeline are complete.
