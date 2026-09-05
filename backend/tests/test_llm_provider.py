"""Tests for the provider-independent LLM client."""

import json
import time

import httpx2 as httpx
import pytest
from pydantic import BaseModel

from app.core.config import Settings
from app.core.llm import (
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    LLMProviderError,
    MockLLMClient,
    OpenAICompatibleLLMClient,
    get_llm_client,
)
from app.schemas.llm import LLMMessage


class _StructuredAnswer(BaseModel):
    answer: str


def _messages(user_content: str = "Summarize the source.") -> list[LLMMessage]:
    return [
        LLMMessage(role="system", content="You are a helpful assistant."),
        LLMMessage(role="user", content=user_content),
    ]


def test_mock_llm_client_is_deterministic() -> None:
    client = MockLLMClient()

    first = client.complete(_messages("alpha"))
    second = client.complete(_messages("alpha"))
    different = client.complete(_messages("beta"))

    assert first.content == second.content
    assert first.content != different.content
    assert first.mocked is True


def test_get_llm_client_returns_mock_by_default() -> None:
    settings = Settings()

    client = get_llm_client(settings)

    assert isinstance(client, MockLLMClient)


def test_get_llm_client_requires_config_when_not_mocked() -> None:
    settings = Settings(mock_llm=False)

    with pytest.raises(LLMProviderError):
        get_llm_client(settings)


def test_get_llm_client_rejects_empty_api_key_when_not_mocked() -> None:
    settings = Settings(
        mock_llm=False,
        llm_base_url="https://example.test/v1",
        llm_api_key=" ",
        llm_model="test-model",
    )

    with pytest.raises(LLMProviderError):
        get_llm_client(settings)


def test_get_llm_client_returns_real_provider_when_configured() -> None:
    settings = Settings(
        mock_llm=False,
        llm_base_url="https://example.test/v1",
        llm_api_key="sk-test",
        llm_model="test-model",
    )

    client = get_llm_client(settings)

    assert isinstance(client, OpenAICompatibleLLMClient)


def test_openai_compatible_client_parses_successful_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "hello from the model"}}]},
        )

    client = OpenAICompatibleLLMClient(
        base_url="https://example.test/v1",
        api_key="sk-test",
        model="test-model",
        transport=httpx.MockTransport(handler),
    )

    completion = client.complete(_messages())

    assert completion.content == "hello from the model"
    assert completion.mocked is False


def test_structured_completion_requests_json_mode_and_accepts_a_json_fence() -> None:
    captured_payload: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_payload.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": '```json\n{"answer":"ready"}\n```'}}
                ]
            },
        )

    client = OpenAICompatibleLLMClient(
        base_url="https://example.test/v1",
        api_key="sk-test",
        model="test-model",
        transport=httpx.MockTransport(handler),
    )

    result = client.complete_structured(_messages(), _StructuredAnswer)

    assert result.answer == "ready"
    assert captured_payload["response_format"] == {"type": "json_object"}


def test_mock_structured_completion_uses_the_explicit_deterministic_factory() -> None:
    result = MockLLMClient().complete_structured(
        _messages(),
        _StructuredAnswer,
        mock_factory=lambda: _StructuredAnswer(answer="offline"),
    )

    assert result.answer == "offline"


def test_openai_compatible_client_retries_then_succeeds() -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        attempts["count"] += 1
        if attempts["count"] < 2:
            return httpx.Response(500, json={"error": "temporary"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    client = OpenAICompatibleLLMClient(
        base_url="https://example.test/v1",
        api_key="sk-test",
        model="test-model",
        transport=httpx.MockTransport(handler),
    )

    completion = client.complete(_messages())

    assert completion.content == "ok"
    assert attempts["count"] == 2


def test_openai_compatible_clients_share_configured_request_pacing() -> None:
    request_times: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        request_times.append(time.monotonic())
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}}]},
        )

    transport = httpx.MockTransport(handler)
    first = OpenAICompatibleLLMClient(
        base_url="https://paced.example.test/v1",
        api_key="sk-test",
        model="paced-model",
        min_request_interval_seconds=0.02,
        transport=transport,
    )
    second = OpenAICompatibleLLMClient(
        base_url="https://paced.example.test/v1",
        api_key="sk-test",
        model="paced-model",
        min_request_interval_seconds=0.02,
        transport=transport,
    )

    first.complete(_messages())
    second.complete(_messages())

    assert request_times[1] - request_times[0] >= 0.018


@pytest.mark.parametrize(
    "failure",
    [
        "rate_limit",
        "timeout",
    ],
)
def test_openai_compatible_client_retries_transient_failures(failure: str) -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            if failure == "rate_limit":
                return httpx.Response(429, json={"error": "slow down"})
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    client = OpenAICompatibleLLMClient(
        base_url="https://example.test/v1",
        api_key="sk-test",
        model="test-model",
        transport=httpx.MockTransport(handler),
    )

    assert client.complete(_messages()).content == "ok"
    assert attempts["count"] == 2


def test_openai_compatible_client_retries_malformed_success_response() -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        attempts["count"] += 1
        return httpx.Response(200, json={"choices": []})

    client = OpenAICompatibleLLMClient(
        base_url="https://example.test/v1",
        api_key="sk-test",
        model="test-model",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(LLMProviderError):
        client.complete(_messages())

    assert attempts["count"] == 3


def test_openai_compatible_client_does_not_retry_authentication_error() -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        attempts["count"] += 1
        return httpx.Response(401, json={"error": "unauthorized"})

    client = OpenAICompatibleLLMClient(
        base_url="https://example.test/v1",
        api_key="sk-test",
        model="test-model",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(LLMProviderError, match="rejected"):
        client.complete(_messages())

    assert attempts["count"] == 1


def test_openai_compatible_client_raises_after_exhausting_retries() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(500, json={"error": "down"})

    client = OpenAICompatibleLLMClient(
        base_url="https://example.test/v1",
        api_key="sk-test",
        model="test-model",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(LLMProviderError):
        client.complete(_messages())


def test_the_request_timeout_defaults_to_the_documented_value() -> None:
    client = OpenAICompatibleLLMClient(
        base_url="https://provider.test/v1", api_key="secret", model="m"
    )

    assert client._request_timeout_seconds == DEFAULT_REQUEST_TIMEOUT_SECONDS


def test_a_slower_provider_can_be_given_longer() -> None:
    """A fixed timeout is an assumption about provider speed.

    Providers differ by an order of magnitude on the same prompt. A model that
    reasons before answering spent well over the thirty-second default on the
    analysis prompts, failing every attempt while the provider was still
    working — a rejection would have been retried, but this was simply slow.
    """

    client = OpenAICompatibleLLMClient(
        base_url="https://provider.test/v1",
        api_key="secret",
        model="m",
        request_timeout_seconds=120.0,
    )

    assert client._request_timeout_seconds == 120.0


@pytest.mark.parametrize("invalid", [0, -1.0])
def test_a_non_positive_timeout_is_rejected(invalid: float) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        OpenAICompatibleLLMClient(
            base_url="https://provider.test/v1",
            api_key="secret",
            model="m",
            request_timeout_seconds=invalid,
        )


def test_the_configured_timeout_reaches_the_client() -> None:
    settings = Settings(
        mock_llm=False,
        llm_base_url="https://provider.test/v1",
        llm_api_key="secret",
        llm_model="m",
        llm_request_timeout_seconds=90.0,
    )

    client = get_llm_client(settings)

    assert isinstance(client, OpenAICompatibleLLMClient)
    assert client._request_timeout_seconds == 90.0


def test_the_timeout_is_the_one_actually_used_for_the_request() -> None:
    """The setting must reach httpx, not merely be stored on the client."""

    seen: dict[str, object] = {}

    def record(request: httpx.Request) -> httpx.Response:
        seen["timeout"] = request.extensions.get("timeout")
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}}]},
        )

    client = OpenAICompatibleLLMClient(
        base_url="https://provider.test/v1",
        api_key="secret",
        model="m",
        request_timeout_seconds=45.0,
        transport=httpx.MockTransport(record),
    )
    client.complete([LLMMessage(role="user", content="hello")])

    assert seen["timeout"] == {
        "connect": 45.0,
        "read": 45.0,
        "write": 45.0,
        "pool": 45.0,
    }
