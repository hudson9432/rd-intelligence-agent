"""GitHub repository search tool.

Queries the public GitHub REST search API and maps each item to a
`SourceResult`. Never invents a repository name, owner, or URL: fields the
response omits stay empty.
"""

from datetime import datetime
from typing import Any

import httpx

from app.schemas.source_result import SourceResult, SourceType
from app.tools.dedupe import content_hash, normalize_url
from app.tools.http import get_with_retry

GITHUB_API_URL = "https://api.github.com/search/repositories"


async def search_github(
    query: str,
    max_results: int,
    *,
    client: httpx.AsyncClient,
) -> list[SourceResult]:
    """Search GitHub repositories and return normalized, deduplicated results.

    Raises `app.tools.http.SourceUnavailableError` if the API cannot be
    reached after bounded retries; callers decide how to degrade.
    """

    response = await get_with_retry(
        client,
        GITHUB_API_URL,
        params={
            "q": query,
            "per_page": str(max_results),
        },
        headers={"Accept": "application/vnd.github+json"},
    )
    return parse_response(response.json())


def parse_response(payload: dict[str, Any]) -> list[SourceResult]:
    results: list[SourceResult] = []

    for item in payload.get("items", []):
        url = item.get("html_url")
        title = item.get("full_name")
        if not url or not title:
            continue

        description = item.get("description")
        owner = item.get("owner") or {}
        author = owner.get("login")

        results.append(
            SourceResult(
                source_type=SourceType.GITHUB,
                title=title,
                url=url,
                normalized_url=normalize_url(url),
                content_hash=content_hash(title, description or ""),
                summary=description,
                authors=[author] if author else [],
                published_at=_parse_datetime(item.get("created_at")),
                metadata={
                    "stars": item.get("stargazers_count"),
                    "language": item.get("language"),
                },
            )
        )

    return results


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
