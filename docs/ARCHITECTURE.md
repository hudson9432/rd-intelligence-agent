# Architecture

## Product loop

R&D Intelligence Agent transforms an open-ended research goal into a defensible
decision and a small executable PoC plan.

```mermaid
flowchart LR
    Goal[Research goal] --> Search[Search Agent]
    Search --> Evidence[Evidence Agent]
    Evidence --> Analyst[Analyst Agent]
    Analyst --> Critic[Critic Agent]
    Critic -->|Missing evidence| Search
    Critic -->|Sufficient or limit reached| Decision[Decision Engine]
    Decision --> Action[Action Agent]
    Action --> Brief[Decision brief + PoC plan]
```

## Components

- **Frontend:** Next.js and TypeScript dashboard for missions, progress, evidence,
  decisions, and action plans.
- **API:** FastAPI endpoints with Pydantic request/response contracts.
- **Services:** application operations and provider-independent interfaces.
- **Agents:** narrow roles that consume and return typed state.
- **Tools:** deterministic source retrieval, parsing, hashing, deduplication, and
  optional workflow integrations.
- **Persistence:** SQLite with repository abstractions for the MVP.
- **Orchestration:** LangGraph typed state graph with bounded re-search and an
  optional in-process background API runner.

## Data flow rules

- A `ResearchMission` owns sources, evidence, opportunities, coverage reports,
  a decision, an action plan, and an ordered event stream.
- Source records retain their original URL and normalized content hash.
- Evidence cards point to their source; opportunities and decisions point to
  evidence IDs.
- LLM structured output requests provider JSON mode and is validated through a
  shared typed boundary before persistence or routing.
- Numeric opportunity scores and coverage thresholds are calculated in code.
- Providers are selected from environment configuration and have deterministic
  mocks for tests/demo.

## Failure model

An unavailable source or malformed LLM response becomes a recorded, typed error.
If some sources fail Evidence extraction, verified cards may continue; if every
new source fails, the stage fails explicitly rather than reporting a genuine
`no_viable_direction`. Existing workflow state is preserved, and every
retry/iteration is bounded.
