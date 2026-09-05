"""Bounded-retry HTTP helper shared by external source tools.

Centralizes the timeout/retry/rate-limit handling required by the product
invariant that every external call must fail gracefully and never hang or
retry unboundedly.
"""

import asyncio
import time
from dataclasses import dataclass, field
from threading import Lock
from urllib.parse import urlsplit

import httpx2 as httpx

DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_SECONDS = 0.5
MAX_RETRY_DELAY_SECONDS = 5.0
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


@dataclass
class _HostPacer:
    """Spaces requests to one host across every caller in this process.

    Backoff only reacts after a host has already refused. Public source APIs
    publish a request rate instead, and arXiv enforces its own by stalling
    replies until they hit the read timeout, so bursts cost far more than the
    spacing would: a throttled query burns three timeouts before failing, while
    a paced one succeeds first time.

    A slot is reserved under a plain lock and awaited outside it, so concurrent
    callers stagger rather than queue behind one another, and the pacer works
    whichever event loop or thread a caller happens to be on.
    """

    lock: Lock = field(default_factory=Lock)
    next_request_at: float = 0.0

    async def wait(self, interval_seconds: float) -> None:
        if interval_seconds <= 0:
            return
        with self.lock:
            now = time.monotonic()
            start_at = max(now, self.next_request_at)
            self.next_request_at = start_at + interval_seconds
        delay = start_at - now
        if delay > 0:
            await asyncio.sleep(delay)


_PACERS: dict[str, _HostPacer] = {}
_PACERS_LOCK = Lock()


def _shared_pacer(url: str) -> _HostPacer:
    """One pacer per host, so a slow source never delays a different one."""

    host = urlsplit(url).netloc
    with _PACERS_LOCK:
        return _PACERS.setdefault(host, _HostPacer())


class SourceUnavailableError(Exception):
    """Raised when a source cannot be reached after bounded retries."""


async def get_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
    min_request_interval_seconds: float = 0,
) -> httpx.Response:
    """GET `url` with a bounded number of retries on timeout or 429/5xx.

    Honors a `Retry-After` header when present; otherwise backs off with
    simple exponential delay. Raises `SourceUnavailableError` once attempts
    are exhausted instead of propagating the underlying transport error, so
    callers can degrade gracefully.

    `min_request_interval_seconds` spaces requests to the same host across the
    whole process, including retries. It defaults to off so a caller supplying
    its own transport is never slowed; production callers pass the configured
    interval.
    """

    last_error: Exception | None = None

    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    if backoff_seconds < 0:
        raise ValueError("backoff_seconds must be non-negative")

    pacer = _shared_pacer(url)

    for attempt in range(1, max_attempts + 1):
        await pacer.wait(min_request_interval_seconds)
        try:
            response = await client.get(
                url, params=params, headers=headers, timeout=DEFAULT_TIMEOUT
            )
        except httpx.TimeoutException as exc:
            last_error = exc
        except httpx.TransportError as exc:
            last_error = exc
        else:
            if response.status_code not in RETRYABLE_STATUS_CODES:
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as error:
                    raise SourceUnavailableError(
                        f"{url} returned HTTP {response.status_code}"
                    ) from error
                return response
            last_error = httpx.HTTPStatusError(
                f"Retryable status {response.status_code} from {url}",
                request=response.request,
                response=response,
            )
            retry_after = response.headers.get("Retry-After")
            if retry_after is not None and attempt < max_attempts:
                await asyncio.sleep(
                    _parse_retry_after(retry_after, _backoff(attempt, backoff_seconds))
                )
                continue

        if attempt < max_attempts:
            await asyncio.sleep(_backoff(attempt, backoff_seconds))

    error_name = (
        type(last_error).__name__ if last_error is not None else "unknown error"
    )
    raise SourceUnavailableError(
        f"{url} failed after {max_attempts} attempts ({error_name})"
    )


def _parse_retry_after(value: str, fallback: float) -> float:
    try:
        return min(max(float(value), 0.0), MAX_RETRY_DELAY_SECONDS)
    except ValueError:
        return fallback


def _backoff(attempt: int, backoff_seconds: float) -> float:
    return min(backoff_seconds * (2 ** (attempt - 1)), MAX_RETRY_DELAY_SECONDS)
