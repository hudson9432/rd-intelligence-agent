"""Deterministic URL normalization and content hashing for deduplication."""

import hashlib
from typing import TYPE_CHECKING
from urllib.parse import urlsplit, urlunsplit

if TYPE_CHECKING:
    from app.schemas.source_result import SourceResult

_TRACKING_PARAM_PREFIXES = ("utm_", "ref", "source")


def normalize_url(url: str) -> str:
    """Return a canonical form of `url` so equivalent links compare equal.

    Lowercases scheme/host, drops the fragment, trailing slash, and known
    tracking query parameters, and forces `https` for arxiv/github hosts that
    always redirect to it. This is intentionally conservative: it never
    rewrites the path or invents a canonical ID.
    """

    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower() or "https"
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/") or "/"

    kept_query = [
        pair
        for pair in parts.query.split("&")
        if pair and not pair.split("=", 1)[0].lower().startswith(_TRACKING_PARAM_PREFIXES)
    ]
    query = "&".join(sorted(kept_query))

    return urlunsplit((scheme, netloc, path, query, ""))


def content_hash(*parts: str) -> str:
    """Return a stable sha256 hash over the given text parts.

    Used to detect duplicate results that reach us via different URLs
    (e.g. an arXiv abstract page vs. its PDF link).
    """

    normalized = "\x1f".join(part.strip().lower() for part in parts if part)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def dedupe_results(results: list["SourceResult"]) -> list["SourceResult"]:
    """Drop later duplicates by normalized URL, then by content hash.

    Preserves the input order of first occurrences so callers can rely on
    source priority (e.g. arXiv before GitHub) by ordering their input.
    """

    seen_urls: set[str] = set()
    seen_hashes: set[str] = set()
    deduped: list[SourceResult] = []

    for result in results:
        if result.normalized_url in seen_urls or result.content_hash in seen_hashes:
            continue
        seen_urls.add(result.normalized_url)
        seen_hashes.add(result.content_hash)
        deduped.append(result)

    return deduped
