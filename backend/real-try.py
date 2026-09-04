import asyncio, sys, httpx
from app.tools.arxiv import search_arxiv
from app.tools.github import search_github
from app.tools.http import SourceUnavailableError

async def main():
    query = sys.argv[1] if len(sys.argv) > 1 else "computer use agents"
    async with httpx.AsyncClient() as client:
        for label, fn in [("arXiv", search_arxiv), ("GitHub", search_github)]:
            try:
                for r in await fn(query, 3, client=client):
                    print(f"[{label}] {r.title}\n    {r.url}")
            except SourceUnavailableError as exc:
                print(f"[{label}] 失敗: {exc}")

asyncio.run(main())
