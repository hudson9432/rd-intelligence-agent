# R&D Intelligence Agent

R&D Intelligence Agent is a hackathon project that will turn a high-level
research goal into evidence-backed R&D decisions and an executable proof-of-
concept plan.

The intended product loop is:

> Research → Evidence → Evaluate → Decide → Act

The repository now runs a mission through Search, Evidence, Analyst, and Critic
agents to an evidence-backed PoC candidate. It supports a deterministic offline
mode and an OpenAI-compatible real-model mode. Decision scoring and Action
planning remain explicit placeholders; the project does not claim that those
unfinished stages are model-backed agents.

## Project status

| Area | Status |
| --- | --- |
| Repository and local environments | Complete |
| FastAPI health API and initial schemas | Complete |
| Next.js dashboard with mission list and creation | Complete |
| SQLite persistence and mission APIs | Complete |
| arXiv/GitHub research source tools (`POST /research/search`) | Complete |
| Search Agent query planning and query-history deduplication | Complete |
| Workflow orchestrator (`POST /missions/{id}/run`) | In progress |
| Typed structured LLM output and provider integration | Complete |
| Analyst, Critic, and the Phase C viability gate | Complete |
| Goal to sources to evidence to decision, offline | Complete |
| PoC action plan and Decision Engine scoring | Planned |
| Deterministic offline demo | In progress |

See [the implementation roadmap](docs/ROADMAP.md) for the ordered delivery
phases and [the architecture guide](docs/ARCHITECTURE.md) for system boundaries.

## Repository layout

```text
.
├── backend/
│   ├── app/
│   │   ├── api/          # HTTP routes
│   │   ├── agents/       # Separately testable agent components
│   │   ├── core/         # Configuration and logging
│   │   ├── db/           # SQLite engine and sessions
│   │   ├── models/       # SQLAlchemy persistence models
│   │   ├── prompts/      # Versioned LLM prompts
│   │   ├── schemas/      # Pydantic API/domain schemas
│   │   ├── repositories/ # Typed persistence operations
│   │   ├── services/     # Mission and research-source use cases
│   │   └── tools/        # arXiv, GitHub, HTTP retry, and dedupe tools
│   ├── tests/
│   ├── .env.example
│   └── requirements.txt
├── frontend/
│   ├── app/
│   ├── components/
│   ├── lib/
│   └── types/
├── demo/                 # fixtures/: frozen arXiv/GitHub responses for mock mode
├── docs/                 # Architecture and implementation roadmap
├── AGENTS.md             # Required context and invariants for coding agents
└── CONTRIBUTING.md       # Branch, test, and pull-request workflow
```

## Prerequisites

- Python 3.11 or newer (developed with Python 3.13.7)
- Node.js 20.9 or newer (developed with Node.js 22.14.0)
- npm 10 or newer

No API key is required while `MOCK_LLM=true` (the default).

## Backend setup

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
cp backend/.env.example backend/.env
cd backend
uvicorn app.main:app --reload --port 8000
```

Check the service:

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{"status":"ok","service":"rd-intelligence-agent-backend"}
```

Mission API:

```bash
curl -X POST http://localhost:8000/missions \
  -H 'Content-Type: application/json' \
  -d '{"title":"Computer-use agents","goal":"Find a one-week PoC"}'

curl http://localhost:8000/missions
curl http://localhost:8000/missions/{mission_id}
curl http://localhost:8000/missions/{mission_id}/events
```

Run backend tests from `backend/`:

```bash
../.venv/bin/python -m pytest
```

## Frontend setup

In a separate terminal:

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:3000>. For production verification, run:

```bash
npm run lint
npm run build
npm start
```

## Configuration

Backend configuration is loaded from process environment variables and
`backend/.env`. Copy `backend/.env.example` for local development. Never commit
the populated `.env` file or API keys.

| Variable | Purpose | Default |
| --- | --- | --- |
| `APP_ENV` | Runtime environment name | `development` |
| `LOG_LEVEL` | Python log level | `INFO` |
| `CORS_ORIGINS` | JSON list of allowed frontend origins | `["http://localhost:3000"]` |
| `DATABASE_URL` | SQLAlchemy database URL | `sqlite:///./data/rd_intelligence.db` |
| `DATABASE_ECHO` | Log generated SQL for debugging | `false` |
| `LLM_BASE_URL` | OpenAI-compatible API base URL, normally ending in `/v1` | empty |
| `LLM_API_KEY` | Secret provider credential | empty |
| `LLM_MODEL` | Provider model name | empty |
| `LLM_MIN_REQUEST_INTERVAL_SECONDS` | Process-wide pacing for one provider/model | `0` |
| `MOCK_LLM` | Use the deterministic, offline LLM client | `true` |
| `GITHUB_TOKEN` | Optional GitHub API credential for higher rate limits | empty |
| `MOCK_EXTERNAL_APIS` | Replay deterministic arXiv/GitHub fixtures | `true` |
| `DEMO_MODE` | Future offline end-to-end demo mode | `false` |

## Research source search

`POST /research/search` queries arXiv and GitHub concurrently, normalizes and
deduplicates the combined results, and reports a single unavailable source in
`errors` instead of failing the request:

```bash
curl -X POST http://localhost:8000/research/search \
  -H "Content-Type: application/json" \
  -d '{"query":"transformers","sources":["arxiv","github"],"max_results_per_source":5}'
```

With `MOCK_EXTERNAL_APIS=true` (the default), it replays the fixed responses in
`demo/fixtures/` through the same parsers as the live path, so mock and real
output are structurally identical.

## Running a mission workflow

`POST /missions/{mission_id}/run` executes the mission graph and records every
stage transition as an `AgentEvent`. It waits for the complete result and is
best suited to offline mode, tests, or direct backend calls:

```bash
curl -X POST http://localhost:8000/missions/{mission_id}/run
curl http://localhost:8000/missions/{mission_id}/events
```

For real providers, use the background endpoint so multiple model calls do not
hold one HTTP request open:

```bash
curl -X POST http://localhost:8000/missions/{mission_id}/run/async
curl http://localhost:8000/missions/{mission_id}
curl http://localhost:8000/missions/{mission_id}/events
```

The background request returns `202 Accepted` with `mission_url` and
`events_url`. Poll until the mission status is `completed` or `failed`. The
terminal `workflow_completed` event includes `evidence_count`, `decision`, and
the evidence-linked `poc_candidates` summary.

The graph runs on LangGraph; routing and the re-search bound stay in
deterministic Python, with LangGraph's step limit only as a backstop.

Search, Evidence, and Analysis are real, so a run goes from the mission goal to
planned queries, retrieved sources, persisted evidence, a Phase C handoff, and
a decision — offline, with `MOCK_EXTERNAL_APIS` and `MOCK_LLM` at their
defaults. It stops at a PoC *candidate*: the Decision stage follows the Phase C
gate without scoring, and the Action stage produces no task plan, so the run
reports `action_plan_skipped` rather than inventing one. An unimplemented phase always
returns an empty result rather than plausible-looking data; see
`backend/app/agents/pending_stages.py`.

### Using a real model

Configure `backend/.env` without committing it:

```dotenv
MOCK_LLM=false
LLM_BASE_URL=https://your-openai-compatible-provider.example/v1
LLM_API_KEY=your-secret-key
LLM_MODEL=your-model-name
LLM_MIN_REQUEST_INTERVAL_SECONDS=0
```

The provider must support the Chat Completions endpoint and JSON object response
mode. Structured calls send `response_format: {"type":"json_object"}` and then
validate the response against the relevant Pydantic contract. A response wrapped
in a single Markdown `json` fence is accepted; prose or a schema mismatch fails
the workflow instead of silently becoming `no_viable_direction`.

For Gemini through Google's OpenAI compatibility endpoint, this configuration
has been exercised end to end:

```dotenv
MOCK_LLM=false
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
LLM_API_KEY=your-gemini-api-key
LLM_MODEL=gemini-3.1-flash-lite
LLM_MIN_REQUEST_INTERVAL_SECONDS=4.2
```

Evidence snippets must still come from the source. Provenance matching tolerates
Unicode normalization and whitespace-only changes, but rejects paraphrases,
translations, and invented text. If every retrieved source is rejected, the
Evidence stage reports a provider failure rather than pretending no viable
direction exists.

`MOCK_EXTERNAL_APIS=true` may be kept while using a real LLM. In that mode the
sources are frozen responses previously captured from the real arXiv and GitHub
APIs, while Search/Evidence/Analyst/Critic cognition comes from the configured
model. Set `MOCK_EXTERNAL_APIS=false` as well to query both source APIs live.

Free-tier providers often impose a low requests-per-minute quota. Set
`LLM_MIN_REQUEST_INTERVAL_SECONDS=4.2` for a 15 RPM quota. The limiter is shared
by Search, Evidence, Analyst, and Critic clients in the process, including retry
attempts; paid tiers can leave it at `0`.

## Current placeholders

- `backend/app/agents/pending_stages.py`: the Decision and Action workflow
  stages. Decision follows the Phase C gate without scoring anything, and
  Action produces no plan, so a run ends at a PoC *candidate* rather than a
  task plan.
- Prompts beyond Evidence extraction and Phase C analysis.
- `demo`: a mission reaches a PoC candidate offline, but mock replay ignores
  the query, so the Critic-driven re-search loop is not observable. See
  `demo/README.md`.
- The dashboard shows missions only. Evidence, decision, and action views, and
  live progress from `GET /missions/{id}/events`, are not built.
- The in-process background runner is appropriate for the hackathon demo, but
  it is not a durable distributed job queue: a process restart can interrupt a
  running mission.

## Collaborating

Before implementing a task:

1. Read [AGENTS.md](AGENTS.md), including its product invariants and definition
   of done. Coding agents must also obey any nested `AGENTS.md` files.
2. Review [the roadmap](docs/ROADMAP.md) and choose a scoped GitHub issue.
3. Create a focused branch, avoid overlapping ownership, and update backend and
   frontend contracts together when a schema changes.
4. Follow [CONTRIBUTING.md](CONTRIBUTING.md) and open a pull request using the
   repository template. CI runs backend tests plus frontend lint/build.

Critical rules for every contributor:

- Preserve source provenance from retrieval through final recommendations.
- Keep scoring, coverage, routing, deduplication, and loop limits deterministic.
- Never place secrets in code, logs, fixtures, events, or commits.
- Keep tests offline and deterministic with mock providers.
- Clearly label placeholders and remaining evidence gaps.

## Development and AI disclosure

The repository foundation, collaboration setup, SQLite persistence, and mission
APIs were prepared before the on-site product workflow work. OpenAI Codex was
used to assist with scaffolding, implementation, tests, documentation, and
repository operations. All changes remain visible in Git history.

Current third-party foundations include Python, FastAPI, Pydantic, SQLAlchemy,
SQLite, LangGraph, Next.js, React, TypeScript, arXiv, GitHub, and their locked
package dependencies. Live model providers, datasets, generated media, and
sponsor tools must be added to this disclosure when introduced.

## License

MIT
