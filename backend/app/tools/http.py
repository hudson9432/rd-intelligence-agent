"""Bounded-retry HTTP helper shared by external source tools.

Centralizes the timeout/retry/rate-limit handling required by the product
invariant that every external call must fail gracefully and never hang or
retry unboundedly.
"""

import asyncio

import httpx2 as httpx

DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_SECONDS = 0.5
MAX_RETRY_DELAY_SECONDS = 5.0
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


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
) -> httpx.Response:
    """GET `url` with a bounded number of retries on timeout or 429/5xx.

    Honors a `Retry-After` header when present; otherwise backs off with
    simple exponential delay. Raises `SourceUnavailableError` once attempts
    are exhausted instead of propagating the underlying transport error, so
    callers can degrade gracefully.
    """

    last_error: Exception | None = None

    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    if backoff_seconds < 0:
        raise ValueError("backoff_seconds must be non-negative")

    for attempt in range(1, max_attempts + 1):
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
