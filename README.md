# R&D Intelligence Agent

R&D Intelligence Agent is a hackathon project that will turn a high-level
research goal into evidence-backed R&D decisions and an executable proof-of-
concept plan.

The intended product loop is:

> Research → Evidence → Evaluate → Decide → Act

This repository currently contains the **phase 1 foundation**: a FastAPI
backend with configuration and health checks, plus a Next.js dashboard shell.
Database persistence, external research providers, LLM calls, agents, and the
workflow are placeholders for later phases.

## Project status

| Area | Status |
| --- | --- |
| Repository and local environments | Complete |
| FastAPI health API and initial schemas | Complete |
| Next.js dashboard shell | Complete |
| SQLite persistence and mission APIs | Next |
| arXiv/GitHub research source tools (`POST /research/search`) | Complete |
| LLM providers and agents | Planned |
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
│   │   ├── db/           # Placeholder: persistence setup
│   │   ├── models/       # Placeholder: database models
│   │   ├── prompts/      # Placeholder: versioned LLM prompts
│   │   ├── schemas/      # Pydantic API/domain schemas
│   │   ├── services/     # research_source.py: arXiv/GitHub search orchestration
│   │   └── tools/        # arxiv.py, github.py, http.py, dedupe.py
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
| `LLM_BASE_URL` | OpenAI-compatible endpoint placeholder | empty |
| `LLM_API_KEY` | Secret provider credential placeholder | empty |
| `LLM_MODEL` | Model name placeholder | empty |
| `MOCK_LLM` | Future deterministic LLM mode | `true` |
| `MOCK_EXTERNAL_APIS` | Replay `demo/fixtures/` instead of calling arXiv/GitHub | `true` |
| `DEMO_MODE` | Future offline end-to-end demo mode | `false` |

## Research source search

`POST /research/search` queries arXiv and GitHub concurrently, normalizes and
deduplicates the combined results, and reports a single unavailable source in
`errors` instead of failing the request:

```bash
curl -X POST http://localhost:8000/research/search \
  -H "Content-Type: application/json" \
  -d '{"query": "transformers", "max_results": 10}'
```

With `MOCK_EXTERNAL_APIS=true` (the default), it replays the fixed responses in
`demo/fixtures/` through the same parsers as the live path, so mock and real
output are structurally identical.

## Current placeholders

- `backend/app/agents`: Orchestrator, Search, Evidence, Analyst, Critic, and
  Action agents.
- `backend/app/db` and `backend/app/models`: SQLite persistence.
- `backend/app/prompts`: prompts kept separate from business logic.
- `docs`: architecture notes. `demo/`: research-source fixtures exist; the full
  end-to-end demo scenario is still planned (phase 14).
- The dashboard's **New Research Mission** action remains disabled until the
  mission API is implemented.

## Collaborating

Before implementing a task:

1. Read [AGENTS.md](AGENTS.md), including its product invariants and definition
   of done. Coding agents must also obey any nested `AGENTS.md` files.
2. Review [the roadmap](docs/ROADMAP.md) and choose a scoped GitHub issue. The
   next planned phase is SQLite persistence and mission APIs.
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

## License

MIT
