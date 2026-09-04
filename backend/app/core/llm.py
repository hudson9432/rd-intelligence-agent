"""Provider-independent LLM client with a deterministic mock implementation."""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod

import httpx2 as httpx

from app.core.config import Settings
from app.schemas.llm import LLMCompletion, LLMMessage

REQUEST_TIMEOUT_SECONDS = 30.0
MAX_ATTEMPTS = 3


class LLMProviderError(RuntimeError):
    """Raised when an LLM provider is misconfigured or fails after all retries."""


class LLMClient(ABC):
    """Chat-completion interface shared by every LLM provider implementation."""

    @abstractmethod
    def complete(self, messages: list[LLMMessage]) -> LLMCompletion:
        raise NotImplementedError


class MockLLMClient(LLMClient):
    """Deterministic, offline stand-in used for tests and demo mode.

    Never performs network I/O. The response is derived only from the input
    messages, so identical input always produces identical output.
    """

    model_name = "mock-llm"

    def complete(self, messages: list[LLMMessage]) -> LLMCompletion:
        transcript = "\n".join(f"{message.role}:{message.content}" for message in messages)
        digest = hashlib.sha256(transcript.encode("utf-8")).hexdigest()[:12]
        last_user_content = next(
            (message.content for message in reversed(messages) if message.role == "user"),
            "",
        )
        return LLMCompletion(
            content=f"[mock-llm:{digest}] {last_user_content}",
            model=self.model_name,
            mocked=True,
        )


class OpenAICompatibleLLMClient(LLMClient):
    """Chat-completion client for an OpenAI-compatible HTTP endpoint."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._transport = transport

    def complete(self, messages: list[LLMMessage]) -> LLMCompletion:
        payload = {
            "model": self._model,
            "messages": [message.model_dump() for message in messages],
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}

        last_error: Exception | None = None
        for _ in range(MAX_ATTEMPTS):
            try:
                with httpx.Client(
                    timeout=REQUEST_TIMEOUT_SECONDS, transport=self._transport
                ) as client:
                    response = client.post(
                        f"{self._base_url}/chat/completions",
                        json=payload,
                        headers=headers,
                    )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
            except (httpx.HTTPError, KeyError, IndexError, TypeError) as error:
                last_error = error
                continue
            return LLMCompletion(content=content, model=self._model, mocked=False)

        raise LLMProviderError(
            f"LLM provider request failed after {MAX_ATTEMPTS} attempts"
        ) from last_error


def get_llm_client(settings: Settings) -> LLMClient:
    """Select the deterministic mock client or a real provider from settings."""

    if settings.mock_llm:
        return MockLLMClient()

    if not settings.llm_base_url or not settings.llm_model or settings.llm_api_key is None:
        raise LLMProviderError(
            "LLM_BASE_URL, LLM_API_KEY, and LLM_MODEL must be set when MOCK_LLM=false"
        )

    return OpenAICompatibleLLMClient(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key.get_secret_value(),
        model=settings.llm_model,
    )
