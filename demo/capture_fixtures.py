"""Capture live arXiv and GitHub responses as deterministic demo fixtures.

This is the one place in the repository that talks to a real external API, and
it is never run by the application or the test suite. Run it by hand when the
demo scenario changes; everything else replays what it writes.

Fixtures hold the raw response bodies, not parsed output, so mock mode feeds
the same parsers as the live path and the two cannot drift. Request URLs and
parameters are imported from the tools themselves for the same reason.

Why capture rather than hand-write: `demo/fixtures/` stands in for real papers
and repositories. Writing an abstract by hand would fabricate source text,
which invariant 1 in `AGENTS.md` forbids, and the Evidence Agent quotes
verbatim from these bodies.

    python demo/capture_fixtures.py --query "on-device llm quantization"

Reaching a PoC candidate offline needs abstracts that state a limitation: the
Critic can only stop asking for more research once evidence records one. The
script reports how many captured sources contain a limitation marker so a
query that yields none is visible immediately rather than at demo time.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))

import httpx2 as httpx  # noqa: E402

from app.agents.evidence import stated_limitation  # noqa: E402
from app.tools.arxiv import ARXIV_API_URL, parse_feed  # noqa: E402
from app.tools.github import GITHUB_API_URL, parse_response  # noqa: E402

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
ARXIV_FIXTURE = FIXTURES_DIR / "arxiv_response.xml"
GITHUB_FIXTURE = FIXTURES_DIR / "github_response.json"

REQUEST_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)


async def capture_arxiv(client: httpx.AsyncClient, query: str, limit: int) -> str:
    response = await client.get(
        ARXIV_API_URL,
        params={
            "search_query": f"all:{query}",
            "start": "0",
            "max_results": str(limit),
        },
    )
    response.raise_for_status()
    return response.text


async def capture_github(client: httpx.AsyncClient, query: str, limit: int) -> str:
    response = await client.get(
        GITHUB_API_URL,
        params={"q": query, "per_page": str(limit)},
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    response.raise_for_status()
    # Re-serialize so the committed fixture is readable in review and diffs.
    return json.dumps(response.json(), indent=2, ensure_ascii=False) + "\n"


def report(label: str, results: list) -> int:
    """Print each captured source and return how many state a limitation."""

    with_limitation = 0
    print(f"\n{label}: {len(results)} source(s)")
    for result in results:
        text = result.content or result.summary or result.title
        limitation = stated_limitation(text) if text else None
        if limitation:
            with_limitation += 1
        marker = "limitation" if limitation else "  --      "
        print(f"  [{marker}] {result.title[:64]}")
    return with_limitation


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--query",
        required=True,
        help="Search query, shared by both sources.",
    )
    parser.add_argument(
        "--limit", type=int, default=5, help="Results per source (default 5)."
    )
    parser.add_argument(
        "--arxiv-only", action="store_true", help="Skip the GitHub capture."
    )
    parser.add_argument(
        "--github-only", action="store_true", help="Skip the arXiv capture."
    )
    args = parser.parse_args()

    capture_arxiv_enabled = not args.github_only
    capture_github_enabled = not args.arxiv_only
    total_with_limitation = 0
    total_sources = 0

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        if capture_arxiv_enabled:
            body = await capture_arxiv(client, args.query, args.limit)
            # Parse before writing: a fixture the tools cannot read is worse
            # than no new fixture.
            results = parse_feed(body)
            if not results:
                print("arXiv returned no parseable entries; not writing.")
                return 1
            ARXIV_FIXTURE.write_text(body, encoding="utf-8")
            total_with_limitation += report(f"arXiv -> {ARXIV_FIXTURE.name}", results)
            total_sources += len(results)

        if capture_github_enabled:
            body = await capture_github(client, args.query, args.limit)
            results = parse_response(json.loads(body))
            if not results:
                print("GitHub returned no parseable items; not writing.")
                return 1
            GITHUB_FIXTURE.write_text(body, encoding="utf-8")
            total_with_limitation += report(f"GitHub -> {GITHUB_FIXTURE.name}", results)
            total_sources += len(results)

    print(
        f"\n{total_with_limitation} of {total_sources} captured source(s) state a "
        "limitation."
    )
    if total_with_limitation == 0:
        print(
            "None do, so an offline run will stop at research_required. Try a "
            "query whose abstracts discuss caveats."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
