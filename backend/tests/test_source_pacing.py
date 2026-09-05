"""Requests to one source are spaced, so a burst never provokes throttling.

arXiv enforces its published rate by stalling replies until they hit the read
timeout. A live round fired four queries with no gap and lost every one: three
timeouts each, then `SourceUnavailableError`, then a re-search round that
looked like it had simply found nothing. Waiting longer does not help — with a
60s read timeout the same query returns HTTP 429 in one second — so the fix is
to not burst in the first place.
"""

import asyncio
import time

import httpx2 as httpx
import pytest
from app.tools import http as http_module
from app.tools.http import SourceUnavailableError, get_with_retry

INTERVAL = 0.05


@pytest.fixture(autouse=True)
def isolated_pacers():
    """Pacers are process-wide; keep one test's timing out of the next."""

    saved = dict(http_module._PACERS)
    http_module._PACERS.clear()
    yield
    http_module._PACERS.clear()
    http_module._PACERS.update(saved)


def always_ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, text="ok")


async def elapsed_for(urls: list[str], *, interval: float) -> float:
    transport = httpx.MockTransport(always_ok)
    async with httpx.AsyncClient(transport=transport) as client:
        started = time.monotonic()
        for url in urls:
            await get_with_retry(client, url, min_request_interval_seconds=interval)
        return time.monotonic() - started


async def test_requests_to_one_host_are_spaced() -> None:
    url = "https://export.arxiv.org/api/query"

    elapsed = await elapsed_for([url, url, url], interval=INTERVAL)

    # First goes immediately; the next two wait their turn.
    assert elapsed >= INTERVAL * 2


async def test_a_slow_host_does_not_delay_a_different_one() -> None:
    """Per-host pacing: GitHub must not queue behind arXiv."""

    arxiv = "https://export.arxiv.org/api/query"
    github = "https://api.github.com/search/repositories"

    elapsed = await elapsed_for([arxiv, github, arxiv, github], interval=INTERVAL)

    # Two requests per host, so only one interval each, not three.
    assert elapsed < INTERVAL * 3


async def test_pacing_is_off_by_default() -> None:
    """A caller with its own transport is never slowed."""

    url = "https://example.test/x"

    elapsed = await elapsed_for([url, url, url], interval=0)

    assert elapsed < INTERVAL


async def test_concurrent_callers_stagger_rather_than_collide() -> None:
    """Reserving the slot under a lock keeps parallel callers in single file."""

    url = "https://export.arxiv.org/api/query"
    transport = httpx.MockTransport(always_ok)

    async with httpx.AsyncClient(transport=transport) as client:
        started = time.monotonic()
        await asyncio.gather(
            *(
                get_with_retry(client, url, min_request_interval_seconds=INTERVAL)
                for _ in range(3)
            )
        )
        elapsed = time.monotonic() - started

    assert elapsed >= INTERVAL * 2


async def test_retries_are_paced_too() -> None:
    """A retry is another request to the same host and must wait its turn."""

    url = "https://export.arxiv.org/api/query"

    def always_throttled(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="slow down")

    transport = httpx.MockTransport(always_throttled)
    async with httpx.AsyncClient(transport=transport) as client:
        started = time.monotonic()
        with pytest.raises(SourceUnavailableError):
            await get_with_retry(
                client,
                url,
                max_attempts=3,
                backoff_seconds=0,
                min_request_interval_seconds=INTERVAL,
            )
        elapsed = time.monotonic() - started

    # Three attempts, so two intervals, even with backoff disabled.
    assert elapsed >= INTERVAL * 2
