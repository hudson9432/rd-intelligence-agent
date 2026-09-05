"""arXiv search tool.

Queries the public arXiv Atom API and maps each entry to a `SourceResult`.
Never invents a title, author, or URL: fields the feed omits stay empty.
"""

from datetime import UTC, datetime
from xml.etree import ElementTree

import httpx2 as httpx

from app.schemas.source_result import SourceResult, SourceType
from app.tools.http import SourceUnavailableError, get_with_retry

ARXIV_API_URL = "https://export.arxiv.org/api/query"
_ATOM_NS = "{http://www.w3.org/2005/Atom}"


async def search_arxiv(
    query: str,
    max_results: int,
    *,
    client: httpx.AsyncClient,
    min_request_interval_seconds: float = 0,
) -> list[SourceResult]:
    """Search arXiv and return normalized, deduplicated results.

    Raises `app.tools.http.SourceUnavailableError` if the API cannot be
    reached after bounded retries; callers decide how to degrade.
    """

    response = await get_with_retry(
        client,
        ARXIV_API_URL,
        params={
            "search_query": f"all:{query}",
            "start": "0",
            "max_results": str(max_results),
        },
        min_request_interval_seconds=min_request_interval_seconds,
    )
    try:
        return parse_feed(response.text)
    except ElementTree.ParseError as error:
        raise SourceUnavailableError("arXiv returned malformed XML") from error


def parse_feed(feed_xml: str) -> list[SourceResult]:
    root = ElementTree.fromstring(feed_xml)
    results: list[SourceResult] = []

    for entry in root.findall(f"{_ATOM_NS}entry"):
        url = _text(entry, "id")
        title = _text(entry, "title")
        if not url or not title:
            continue

        title = " ".join(title.split())
        summary_raw = _text(entry, "summary")
        summary = " ".join(summary_raw.split()) if summary_raw else None
        authors = [
            name.strip()
            for author in entry.findall(f"{_ATOM_NS}author")
            if (name := _text(author, "name")) is not None
        ]
        published = _parse_datetime(_text(entry, "published"))

        results.append(
            SourceResult(
                source_type=SourceType.ARXIV,
                title=title,
                url=url,
                summary=summary,
                authors=authors,
                published_at=published,
            )
        )

    return results


def _text(node: ElementTree.Element, tag: str) -> str | None:
    child = node.find(f"{_ATOM_NS}{tag}")
    return child.text.strip() if child is not None and child.text else None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)
