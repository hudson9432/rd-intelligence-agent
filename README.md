# R&D Intelligence Agent

R&D Intelligence Agent is a hackathon project that will turn a high-level
research goal into evidence-backed R&D decisions and an executable proof-of-
concept plan.

The intended product loop is:

> Research → Evidence → Evaluate → Decide → Act

This repository currently contains the **phase 1–2 foundation**: a FastAPI
backend, SQLite persistence and mission APIs, plus a Next.js dashboard shell.
External research providers, LLM calls, agents, and the workflow are
placeholders for later phases.

## Project status

| Area | Status |
| --- | --- |
| Repository and local environments | Complete |
| FastAPI health API and initial schemas | Complete |
| Next.js dashboard shell | Complete |
| SQLite persistence and mission APIs | Complete |
| Research tools, LLM providers, and agents | Planned |
| Deterministic offline demo | Planned |

See [the implementation roadmap](docs/ROADMAP.md) for the ordered delivery
phases and [the architecture guide](docs/ARCHITECTURE.md) for system boundaries.

## Repository layout

```text
.
├── backend/
│   ├── app/
│   │   ├── api/          # HTTP routes
│   │   ├── agents/       # Placeholder: agent implementations
│   │   ├── core/         # Configuration and logging
│   │   ├── db/           # SQLite engine and sessions
│   │   ├── models/       # SQLAlchemy persistence models
│   │   ├── prompts/      # Placeholder: versioned LLM prompts
│   │   ├── schemas/      # Pydantic API/domain schemas
│   │   ├── repositories/ # Typed persistence operations
│   │   ├── services/     # Mission application service
│   │   └── tools/        # Placeholder: deterministic source tools
│   ├── tests/
│   ├── .env.example
│   └── requirements.txt
├── frontend/
│   ├── app/
│   ├── components/
│   ├── lib/
│   └── types/
├── demo/                 # Placeholder: offline demo fixtures
├── docs/                 # Architecture and implementation roadmap
├── AGENTS.md             # Required context and invariants for coding agents
└── CONTRIBUTING.md       # Branch, test, and pull-request workflow
```

## Prerequisites

- Python 3.11 or newer (developed with Python 3.13.7)
- Node.js 20.9 or newer (developed with Node.js 22.14.0)
- npm 10 or newer

No API key is required for the current phase.

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
| `LLM_BASE_URL` | OpenAI-compatible endpoint placeholder | empty |
| `LLM_API_KEY` | Secret provider credential placeholder | empty |
| `LLM_MODEL` | Model name placeholder | empty |
| `MOCK_LLM` | Future deterministic LLM mode | `true` |
| `MOCK_EXTERNAL_APIS` | Future deterministic source mode | `true` |
| `DEMO_MODE` | Future offline end-to-end demo mode | `false` |

## Current placeholders

- `backend/app/agents`: Orchestrator, Search, Evidence, Analyst, Critic, and
  Action agents.
- `backend/app/tools`: deterministic external research-source tools.
- Most `backend/app/services` modules beyond the mission service.
- `backend/app/prompts`: prompts kept separate from business logic.
- `docs` and `demo`: architecture notes and deterministic demo fixtures.
- The dashboard's **New Research Mission** action remains disabled until the
  frontend workflow phase connects it to the implemented mission API.

## Collaborating

Before implementing a task:

1. Read [AGENTS.md](AGENTS.md), including its product invariants and definition
   of done. Coding agents must also obey any nested `AGENTS.md` files.
2. Review [the roadmap](docs/ROADMAP.md) and choose a scoped GitHub issue. The
   next planned phase is arXiv and GitHub research-source tools.
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
SQLite, Next.js, React, TypeScript, and their locked package dependencies. Live
research sources, model providers, datasets, generated media, and sponsor tools
must be added to this disclosure when introduced.

## License

MIT
