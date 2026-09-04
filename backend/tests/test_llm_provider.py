"""Tests for the provider-independent LLM client."""

import httpx2 as httpx
import pytest

from app.core.config import Settings
from app.core.llm import (
    LLMProviderError,
    MockLLMClient,
    OpenAICompatibleLLMClient,
    get_llm_client,
)
from app.schemas.llm import LLMMessage


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
