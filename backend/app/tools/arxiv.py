"""arXiv search tool.

Queries the public arXiv Atom API and maps each entry to a `SourceResult`.
Never invents a title, author, or URL: fields the feed omits stay empty.
"""

from datetime import datetime
from xml.etree import ElementTree

import httpx

from app.schemas.source_result import SourceResult, SourceType
from app.tools.dedupe import content_hash, normalize_url
from app.tools.http import get_with_retry

ARXIV_API_URL = "https://export.arxiv.org/api/query"
_ATOM_NS = "{http://www.w3.org/2005/Atom}"


async def search_arxiv(
    query: str,
    max_results: int,
    *,
    client: httpx.AsyncClient,
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
    )
    return parse_feed(response.text)


def parse_feed(feed_xml: str) -> list[SourceResult]:
    root = ElementTree.fromstring(feed_xml)  # noqa: S314 - trusted arXiv API response
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
                normalized_url=normalize_url(url),
                content_hash=content_hash(title, summary or ""),
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
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
