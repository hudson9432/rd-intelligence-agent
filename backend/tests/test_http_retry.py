"""Tests for the bounded-retry HTTP helper shared by external source tools."""

import httpx
import pytest

from app.tools.http import DEFAULT_TIMEOUT, SourceUnavailableError, get_with_retry


@pytest.fixture(autouse=True)
def _no_real_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip real sleep delays so retry tests run fast."""

    async def fast_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("app.tools.http.asyncio.sleep", fast_sleep)


async def test_get_with_retry_returns_response_on_first_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="ok")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        response = await get_with_retry(client, "https://example.com/x")

    assert response.text == "ok"


async def test_get_with_retry_recovers_after_transient_failures() -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, text="recovered")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        response = await get_with_retry(client, "https://example.com/x", max_attempts=3)

    assert response.text == "recovered"
    assert attempts["count"] == 3


async def test_get_with_retry_raises_after_exhausting_attempts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SourceUnavailableError):
            await get_with_retry(client, "https://example.com/x", max_attempts=2)


async def test_get_with_retry_does_not_retry_client_errors() -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await get_with_retry(client, "https://example.com/x", max_attempts=3)

    assert attempts["count"] == 1


async def test_get_with_retry_applies_a_bounded_timeout() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, text="ok")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await get_with_retry(client, "https://example.com/x")

    timeout = captured["request"].extensions["timeout"]
    assert timeout["connect"] == DEFAULT_TIMEOUT.connect
    assert timeout["read"] == DEFAULT_TIMEOUT.read


async def test_get_with_retry_retries_timeouts_then_gives_up() -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        raise httpx.ReadTimeout("too slow", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SourceUnavailableError):
            await get_with_retry(client, "https://example.com/x", max_attempts=3)

    assert attempts["count"] == 3


async def test_get_with_retry_honors_retry_after_header() -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, text="ok")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        response = await get_with_retry(client, "https://example.com/x", max_attempts=3)

    assert response.text == "ok"
    assert attempts["count"] == 2
