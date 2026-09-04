# Demo fixtures

`fixtures/arxiv_response.xml` and `fixtures/github_response.json` hold raw
responses captured from the real arXiv and GitHub APIs. `ResearchSourceService`
replays them whenever `MOCK_EXTERNAL_APIS=true` (the default), feeding them
through the exact same parsers as the live path (`app/tools/arxiv.py`,
`app/tools/github.py`) so mock and real output cannot drift.

## Refreshing them

`capture_fixtures.py` is the one place in the repository that calls a real
external API. The application and the test suite never do.

```bash
.venv/bin/python demo/capture_fixtures.py --query "your search" --limit 6
```

It imports the request URLs and parameters from the tools themselves, parses
each response before writing it, and reports how many captured sources state a
limitation.

**Do not hand-write fixture content.** These files stand in for real papers and
repositories, and the Evidence Agent quotes them verbatim; authoring an abstract
would fabricate source text, which invariant 1 in `AGENTS.md` forbids.

## What makes a fixture set usable

`backend/tests/test_demo_fixtures.py` guards the properties a refresh must
preserve, so a bad capture fails the suite rather than the demo:

- Both sources parse with no errors.
- Most sources score above zero relevance against the demo goal. Some will
  score zero — `goal_overlap` is lexical, so a description saying "RAG" where
  the goal says "retrieval augmented generation" scores zero offline.
- **At least half state a limitation.** The Critic keeps asking for more
  research until evidence records a caveat, so a set of limitation-free
  abstracts can never reach a PoC candidate however well the agents work.
  Prefer queries whose abstracts discuss failure modes or evaluation limits.
- The offline run reaches `ready_for_poc` deterministically.

If a refresh breaks the demo, those tests say which property was lost.

## What is still missing

Mock replay ignores the query: the fixtures are returned whatever is asked for.
A targeted re-search round therefore returns exactly the same sources it
already has, so the bounded re-search loop cannot improve its evidence offline
and the product's Critic-driven re-search story is not observable in mock mode.

Making that work needs per-query fixture sets, and is the remaining piece of
roadmap phase 14 along with the full mission-to-action-plan demo scenario.
