# Demo fixtures

`fixtures/arxiv_response.xml` and `fixtures/github_response.json` hold raw
responses captured from the real arXiv and GitHub APIs. `ResearchSourceService`
replays them whenever `MOCK_EXTERNAL_APIS=true` (the default), feeding them
through the exact same parsers as the live path (`app/tools/arxiv.py`,
`app/tools/github.py`) so mock and real output cannot drift.

`fixtures/ecommerce_recommender_pro_con_arxiv_response.xml` is a separate,
exact-ID capture for the contested e-commerce scenario. Its companion
`ecommerce_recommender_scenario.json` assigns two papers to support and two to
challenge one recommendation claim, and records the important questions the
PoC must answer. Each question includes a proposed experiment, metrics,
controls, explicit pass/fail conditions, and the provenance of those
thresholds. The role assignment, questions, and acceptance thresholds are
scenario metadata; all titles, abstracts, authors, dates, URLs, and reported
source metrics remain verbatim from the captured arXiv response.

## Refreshing them

`capture_fixtures.py` is the one place in the repository that calls a real
external API. The application and the test suite never do.

```bash
.venv/bin/python demo/capture_fixtures.py --query "your search" --limit 6
```

Refresh the e-commerce capture without changing the default RAG fixtures:

```bash
.venv/bin/python demo/capture_fixtures.py \
  --arxiv-ids 2108.05891 2507.15113 2308.01118 1911.07698 \
  --arxiv-only --fixture-stem ecommerce_recommender_pro_con
```

Refresh the targeted RAG follow-up papers by exact ID:

```bash
.venv/bin/python demo/capture_fixtures.py \
  --arxiv-ids 2401.00396 2408.08067 2410.14479 \
  --arxiv-only --fixture-stem rag_targeted_research
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

## Query-aware re-search profile

`fixtures/rag_targeted_research_arxiv_response.xml` is a second raw capture for
Critic follow-up queries about citations, hallucinations, Ragas, prompt
injection, or failure benchmarks. General first-pass queries replay the default
arXiv/GitHub fixtures; those targeted queries replay the follow-up papers, so a
second round adds distinct evidence instead of re-extracting the same sources.

This is intentionally a small deterministic profile, not a fake search index.
Queries outside those RAG concepts still use the default fixture set. The
e-commerce scenario test continues to exercise its exact captured sources
directly through Phase C and Action; it is not automatically selected by mock
Search.
