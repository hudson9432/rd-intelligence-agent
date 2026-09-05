# Agent Collaboration Guide

This file is the primary operating context for coding agents working in this
repository. Read it before changing code. Also read any nested `AGENTS.md`
that applies to the files you touch; nested instructions take precedence.

## Product mission

Build **R&D Intelligence Agent**, a multi-agent system that turns a high-level
research goal into an evidence-backed R&D decision and an executable PoC plan:

> Research → Evidence → Evaluate → Decide → Act

The product is not a generic summarizer. Its differentiators are source
provenance, a Critic-driven targeted re-search loop, deterministic scoring and
routing, and a final recommendation that becomes concrete work.

Primary users are R&D leads, product managers, technical strategy teams, and
innovation teams.

## Current state

Phases 1–2 (repository foundation and persistence) are complete:

- FastAPI application, environment settings, logging, and `GET /health`.
- Initial `ResearchMission` and `AgentEvent` Pydantic schemas.
- SQLAlchemy models and repositories for missions, sources, evidence,
  opportunities, coverage reports, action plans, and agent events.
- SQLite initialization with UTC timestamps, JSON fields, provenance checks,
  and mission/source cascade behavior.
- Mission create/list/get and event-list APIs.
- A provider-independent synchronous LLM client, deterministic mock client, and
  an OpenAI-compatible implementation with bounded retries. Structured calls
  request JSON object mode, tolerate one Markdown JSON fence, and validate once
  through a typed Pydantic boundary.
- A standalone Evidence extraction component with Pydantic validation and
  exact source-snippet provenance checks. It takes the mission goal, because
  `relevance_score` is meaningless without one. Offline extraction scores
  relevance by deterministic lexical overlap with the goal and quotes a
  limitation only when the source states one; it never invents a field.
- A LangGraph workflow orchestrator with a bounded re-search loop, persisted
  `AgentEvent` transitions, mission status handling, and
  `POST /missions/{id}/run`. Routing and the iteration limit remain in
  deterministic Python; LangGraph provides the runtime.
- The workflow's Search, Evidence, and Analysis stages are real: Search plans
  bounded, history-aware queries before deterministic retrieval; a mission then
  runs through persisted evidence and a Phase C handoff to a decision, entirely
  offline, and Action turns the selected candidate into a stored PoC task plan.
  Every task must name an open item the candidate carries, so a plan cannot be
  a generic checklist. Only Decision is still provisional: it follows the Phase
  C gate without scoring anything.
- Real-provider runs can use `POST /missions/{id}/run/async`; the in-process
  background worker uses its own database session and exposes progress and its
  terminal summary through persisted mission events.
- Next.js App Router dashboard that lists and creates missions against the
  mission API from a client component, with loading, timeout, and error
  states, covered by Vitest tests in CI. Evidence, decision, and action views
  are not built.
- Tests, pinned direct dependencies, and offline-compatible frontend build.

Phase 3 research-source tools are implemented:

- `SourceResult`/`SourceError` schemas and `POST /research/search`.
- `search_arxiv()` and `search_github()` tools with bounded timeout/retry and
  graceful rate-limit handling (`app/tools/http.py`).
- Normalized-URL and content-hash deduplication (`app/tools/dedupe.py`).
- `MOCK_EXTERNAL_APIS` fixture mode (`demo/fixtures/`) that replays real,
  frozen arXiv/GitHub responses through the live parsers. Mock responses are
  deterministic and honor source selection, per-source limits, and date filters.

The Search, Evidence, Analyst, and Critic agents are wired into the public
mission workflow and can use a real provider. Search uses the LLM only to plan
queries; arXiv/GitHub retrieval and query-history deduplication remain bounded,
deterministic code. Action plans the PoC, but identifiers, dependency
resolution, effort aggregation, and the task ceiling stay in code rather than
being taken from the model. Decision is still provisional, so do not claim the
decision itself is scored. The in-process background runner is not a durable
job queue.

Check [docs/ROADMAP.md](docs/ROADMAP.md) before starting work and update it only
when a phase is genuinely complete.

## Architecture boundaries

```text
frontend (Next.js + TypeScript)
        │ HTTP / future event polling
        ▼
backend API (FastAPI + Pydantic)
        │
        ├── services     application use cases
        ├── agents       separately testable agent roles
        ├── tools        deterministic external integrations
        ├── prompts      prompts, separate from Python business logic
        ├── models/db    SQLite persistence
        └── schemas      API and workflow contracts
```

The planned workflow is:

```text
START → Search → Evidence → Analyst → Critic
                                      ├─ insufficient → targeted re-search
                                      └─ sufficient/max iterations → Decision
                                                                      ↓
                                                                   Action → END
```

Keep orchestration thin. Parsing, deduplication, scoring, coverage calculation,
iteration limits, and routing belong in deterministic, typed code. LLMs may
generate or classify content but must not silently own business rules.

## Non-negotiable product invariants

1. Never fabricate papers, repositories, benchmarks, URLs, metrics, or source
   text.
2. Every factual recommendation must preserve source and evidence IDs.
3. Unknown evidence fields remain null or empty; they are never guessed.
4. API keys and OAuth credentials never enter code, fixtures, logs, events, or
   commits.
5. External calls require timeouts, bounded retries, and graceful failure.
   Provider or structured-output failures must remain distinguishable from a
   genuine evidence-backed `no_viable_direction` outcome.
   Provider rate limits apply across agents sharing the same provider/model;
   configure process-wide request pacing for low-RPM tiers.
6. Research loops must have explicit iteration/query limits.
7. Demo and test modes must be deterministic and make no real external calls.
8. Calendar or other side effects require explicit user approval before
   execution.

## Working conventions

- Keep work scoped to one roadmap phase or clearly bounded issue.
- Coordinate ownership before editing shared contracts or migrations. Avoid
  overlapping broad refactors across agents.
- Preserve public schemas unless the issue explicitly calls for a contract
  change; update backend, frontend types, docs, and tests together when it does.
- Backend code uses explicit types, small modules, timezone-aware UTC timestamps,
  Pydantic validation, and dependency-injected providers.
- Frontend code uses TypeScript strict mode and Server Components by default.
  Read `frontend/AGENTS.md` before frontend changes because the installed Next.js
  version includes version-specific local documentation.
- Keep prompts in `backend/app/prompts/`; do not embed large prompts in agents.
- Reuse repository/service interfaces rather than accessing SQLite from agents.
- Do not add a framework or hosted service when a small local abstraction is
  enough for the MVP. LangGraph is the one accepted exception, for the workflow
  runtime only; see `docs/ROADMAP.md`.
- Never commit `.env`, local databases, caches, `.venv`, or `node_modules`.

## Development commands

Backend setup and tests, from repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
cp backend/.env.example backend/.env
cd backend
../.venv/bin/python -m pytest
../.venv/bin/uvicorn app.main:app --reload --port 8000
```

Frontend setup and verification:

```bash
cd frontend
npm ci
npm run lint
npm run build
npm run dev
```

## Definition of done

A change is complete only when:

- Behavior matches the issue and the architecture/product invariants above.
- New logic has unit tests; workflow changes include an integration test using
  mock providers.
- Backend tests pass and touched frontend code passes lint and production build.
- No real external API is called by tests.
- Configuration is documented in `.env.example` and README without secrets.
- Public contract, architecture, or roadmap changes are documented.
- The handoff/PR states what changed, how it was verified, and any remaining
  limitation without overstating completeness.

## Recommended task order

Follow the numbered roadmap. Search, Evidence, Analyst, Critic, and Action are
now wired; prioritize the real Decision stage, durable execution, and visible
frontend progress without weakening provenance. Calendar integration remains
optional and should be done only after the core research-to-action loop is
reliable.
