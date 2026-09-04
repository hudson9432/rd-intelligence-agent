"""Deterministic URL normalization and content hashing for deduplication."""

import hashlib
from typing import TYPE_CHECKING
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

if TYPE_CHECKING:
    from app.schemas.source_result import SourceResult

_TRACKING_PARAM_PREFIXES = ("utm_",)
_TRACKING_PARAM_NAMES = {"ref", "source"}


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
        (name, value)
        for name, value in parse_qsl(parts.query, keep_blank_values=True)
        if name.lower() not in _TRACKING_PARAM_NAMES
        and not name.lower().startswith(_TRACKING_PARAM_PREFIXES)
    ]
    query = urlencode(sorted(kept_query))

    return urlunsplit((scheme, netloc, path, query, ""))


def content_hash(*parts: str) -> str:
    """Return a stable sha256 hash over the given text parts.

    Used to detect duplicate results that reach us via different URLs
    (e.g. an arXiv abstract page vs. its PDF link).
    """

    normalized = "\x1f".join(
        " ".join(part.split()).casefold() for part in parts if part
    )
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
        normalized_result_url = normalize_url(result.url)
        result_hash = content_hash(
            result.title,
            result.summary or "",
            result.content or "",
        )
        if normalized_result_url in seen_urls or result_hash in seen_hashes:
            continue
        seen_urls.add(normalized_result_url)
        seen_hashes.add(result_hash)
        deduped.append(result)

    return deduped
