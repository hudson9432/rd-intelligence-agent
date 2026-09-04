# Demo fixtures

`fixtures/arxiv_response.xml` and `fixtures/github_response.json` are frozen,
real arXiv/GitHub API responses used by `ResearchSourceService` when
`MOCK_EXTERNAL_APIS=true` (the default). They are fed through the exact same
parsers (`app/tools/arxiv.py`, `app/tools/github.py`) as live responses, so
mock and real output are structurally identical.

The full offline, end-to-end hackathon demo scenario (mission → decision →
action plan) is still planned for the Demo Mode phase (roadmap phase 14).
