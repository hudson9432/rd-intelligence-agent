"""Provider-independent LLM client with a deterministic mock implementation."""

from __future__ import annotations

import hashlib
import re
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Lock
from typing import TypeVar

import httpx2 as httpx
from pydantic import BaseModel, Field, ValidationError

from app.core.config import Settings
from app.schemas.llm import LLMCompletion, LLMMessage

REQUEST_TIMEOUT_SECONDS = 30.0
MAX_ATTEMPTS = 3

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)

_JSON_FENCE = re.compile(
    r"\A```(?:json)?\s*(?P<payload>.*?)\s*```\Z",
    flags=re.IGNORECASE | re.DOTALL,
)


@dataclass
class _RequestPacer:
    """Process-local request pacing shared by clients for one provider/model."""

    lock: Lock = field(default_factory=Lock)
    next_request_at: float = 0

    def wait(self, interval_seconds: float) -> None:
        if interval_seconds <= 0:
            return
        with self.lock:
            delay = self.next_request_at - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            self.next_request_at = time.monotonic() + interval_seconds


_PACERS: dict[tuple[str, str], _RequestPacer] = {}
_PACERS_LOCK = Lock()


def _shared_pacer(base_url: str, model: str) -> _RequestPacer:
    key = (base_url, model)
    with _PACERS_LOCK:
        return _PACERS.setdefault(key, _RequestPacer())


class _ProviderMessage(BaseModel):
    content: str


class _ProviderChoice(BaseModel):
    message: _ProviderMessage


class _ProviderResponse(BaseModel):
    choices: list[_ProviderChoice] = Field(min_length=1)


class LLMProviderError(RuntimeError):
    """Raised when an LLM provider is misconfigured or fails after all retries."""


class LLMStructuredOutputError(RuntimeError):
    """Raised when a completion cannot satisfy a requested Pydantic contract."""


class LLMClient(ABC):
    """Chat-completion interface shared by every LLM provider implementation."""

    @abstractmethod
    def complete(self, messages: list[LLMMessage]) -> LLMCompletion:
        raise NotImplementedError

    def complete_structured(
        self,
        messages: list[LLMMessage],
        response_model: type[StructuredModel],
        *,
        mock_factory: Callable[[], StructuredModel] | None = None,
    ) -> StructuredModel:
        """Return validated structured output from a provider completion.

        Real providers are parsed through one tolerant boundary rather than
        duplicating strict JSON parsing in every agent. Deterministic mock
        behavior remains explicit at each call site through ``mock_factory``.
        """

        completion = self._complete_for_structure(messages)
        if completion.mocked:
            if mock_factory is None:
                raise LLMStructuredOutputError(
                    "Mocked structured completion requires a deterministic factory"
                )
            return mock_factory()

        payload = _strip_json_fence(completion.content)
        try:
            return response_model.model_validate_json(payload)
        except (ValidationError, ValueError) as error:
            raise LLMStructuredOutputError(
                f"LLM response did not match {response_model.__name__}"
            ) from error

    def _complete_for_structure(self, messages: list[LLMMessage]) -> LLMCompletion:
        """Provider hook for requesting JSON mode when it is available."""

        return self.complete(messages)


class MockLLMClient(LLMClient):
    """Deterministic, offline stand-in used for tests and demo mode.

    Never performs network I/O. The response is derived only from the input
    messages, so identical input always produces identical output.
    """

    model_name = "mock-llm"

    def complete(self, messages: list[LLMMessage]) -> LLMCompletion:
        transcript = "\n".join(
            f"{message.role}:{message.content}" for message in messages
        )
        digest = hashlib.sha256(transcript.encode("utf-8")).hexdigest()[:12]
        last_user_content = next(
            (
                message.content
                for message in reversed(messages)
                if message.role == "user"
            ),
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
        min_request_interval_seconds: float = 0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._min_request_interval_seconds = min_request_interval_seconds
        self._transport = transport
        self._pacer = _shared_pacer(self._base_url, self._model)

    def complete(self, messages: list[LLMMessage]) -> LLMCompletion:
        return self._request(messages)

    def _complete_for_structure(self, messages: list[LLMMessage]) -> LLMCompletion:
        return self._request(
            messages,
            response_format={"type": "json_object"},
        )

    def _request(
        self,
        messages: list[LLMMessage],
        *,
        response_format: dict[str, str] | None = None,
    ) -> LLMCompletion:
        payload = {
            "model": self._model,
            "messages": [message.model_dump() for message in messages],
        }
        if response_format is not None:
            payload["response_format"] = response_format
        headers = {"Authorization": f"Bearer {self._api_key}"}

        last_error: Exception | None = None
        with httpx.Client(
            timeout=REQUEST_TIMEOUT_SECONDS, transport=self._transport
        ) as client:
            for _ in range(MAX_ATTEMPTS):
                try:
                    self._pacer.wait(self._min_request_interval_seconds)
                    response = client.post(
                        f"{self._base_url}/chat/completions",
                        json=payload,
                        headers=headers,
                    )
                    response.raise_for_status()
                    provider_response = _ProviderResponse.model_validate(
                        response.json()
                    )
                    content = provider_response.choices[0].message.content
                except httpx.HTTPStatusError as error:
                    status_code = error.response.status_code
                    if 400 <= status_code < 500 and status_code != 429:
                        raise LLMProviderError(
                            "LLM provider rejected the request"
                        ) from error
                    last_error = error
                    continue
                except (
                    httpx.HTTPError,
                    ValidationError,
                    ValueError,
                    IndexError,
                ) as error:
                    last_error = error
                    continue
                return LLMCompletion(content=content, model=self._model, mocked=False)

        raise LLMProviderError(
            f"LLM provider request failed after {MAX_ATTEMPTS} attempts"
        ) from last_error


def _strip_json_fence(content: str) -> str:
    """Remove a single Markdown JSON fence while rejecting surrounding prose."""

    stripped = content.strip()
    match = _JSON_FENCE.fullmatch(stripped)
    return match.group("payload").strip() if match else stripped


def get_llm_client(settings: Settings) -> LLMClient:
    """Select the deterministic mock client or a real provider from settings."""

    if settings.mock_llm:
        return MockLLMClient()

    api_key = (
        settings.llm_api_key.get_secret_value().strip()
        if settings.llm_api_key is not None
        else ""
    )
    if not settings.llm_base_url or not settings.llm_model or not api_key:
        raise LLMProviderError(
            "LLM_BASE_URL, LLM_API_KEY, and LLM_MODEL must be set when MOCK_LLM=false"
        )

    return OpenAICompatibleLLMClient(
        base_url=settings.llm_base_url,
        api_key=api_key,
        model=settings.llm_model,
        min_request_interval_seconds=settings.llm_min_request_interval_seconds,
    )
