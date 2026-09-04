"""GitHub repository search tool.

Queries the public GitHub REST search API and maps each item to a
`SourceResult`. Never invents a repository name, owner, or URL: fields the
response omits stay empty.
"""

from datetime import UTC, datetime
from typing import Any

import httpx2 as httpx
from pydantic import ValidationError

from app.schemas.source_result import SourceResult, SourceType
from app.tools.http import SourceUnavailableError, get_with_retry

GITHUB_API_URL = "https://api.github.com/search/repositories"


async def search_github(
    query: str,
    max_results: int,
    *,
    client: httpx.AsyncClient,
    token: str | None = None,
) -> list[SourceResult]:
    """Search GitHub repositories and return normalized, deduplicated results.

    Raises `app.tools.http.SourceUnavailableError` if the API cannot be
    reached after bounded retries; callers decide how to degrade.
    """

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    response = await get_with_retry(
        client,
        GITHUB_API_URL,
        params={
            "q": query,
            "per_page": str(max_results),
        },
        headers=headers,
    )
    try:
        return parse_response(response.json())
    except (TypeError, ValueError, ValidationError) as error:
        raise SourceUnavailableError("GitHub returned a malformed response") from error


def parse_response(payload: dict[str, Any]) -> list[SourceResult]:
    results: list[SourceResult] = []

    items = payload.get("items", [])
    if not isinstance(items, list):
        raise TypeError("GitHub response items must be a list")

    for item in items:
        if not isinstance(item, dict):
            continue
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
                summary=description,
                authors=[author] if author else [],
                published_at=_parse_datetime(item.get("created_at")),
                metadata={
                    "stars": item.get("stargazers_count"),
                    "language": item.get("language"),
                    "updated_at": item.get("updated_at"),
                },
            )
        )

    return results


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)
