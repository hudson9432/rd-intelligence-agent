"""Tests for the provider-independent LLM client."""

import json
import time

import httpx2 as httpx
import pytest
from pydantic import BaseModel

from app.core.config import Settings
from app.core.llm import (
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    RETRY_BACKOFF_MAX_SECONDS,
    STRUCTURED_OUTPUT_ATTEMPTS,
    LLMProviderError,
    LLMResponseTruncatedError,
    LLMStructuredOutputError,
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
        retry_backoff_seconds=0,
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
        retry_backoff_seconds=0,
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
        retry_backoff_seconds=0,
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
        retry_backoff_seconds=0,
        base_url="https://paced.example.test/v1",
        api_key="sk-test",
        model="paced-model",
        min_request_interval_seconds=0.02,
        transport=transport,
    )
    second = OpenAICompatibleLLMClient(
        retry_backoff_seconds=0,
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
        retry_backoff_seconds=0,
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
        retry_backoff_seconds=0,
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
        retry_backoff_seconds=0,
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
        retry_backoff_seconds=0,
        base_url="https://example.test/v1",
        api_key="sk-test",
        model="test-model",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(LLMProviderError):
        client.complete(_messages())


def test_the_request_timeout_defaults_to_the_documented_value() -> None:
    client = OpenAICompatibleLLMClient(
        retry_backoff_seconds=0,
        base_url="https://provider.test/v1",
        api_key="secret",
        model="m",
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
        retry_backoff_seconds=0,
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
            retry_backoff_seconds=0,
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
        retry_backoff_seconds=0,
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


class _Shape(BaseModel):
    value: int


def structured_client(*bodies: str) -> tuple[OpenAICompatibleLLMClient, list[str]]:
    """A client whose provider returns each body in turn, repeating the last."""

    seen: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        body = bodies[min(len(seen), len(bodies) - 1)]
        seen.append(body)
        return httpx.Response(200, json={"choices": [{"message": {"content": body}}]})

    client = OpenAICompatibleLLMClient(
        retry_backoff_seconds=0,
        base_url="https://provider.test/v1",
        api_key="secret",
        model="m",
        transport=httpx.MockTransport(respond),
    )
    return client, seen


def test_a_response_that_misses_the_contract_is_asked_for_again() -> None:
    """Sampling is stochastic, so one slip should not end a mission.

    A live provider failed a mission after four minutes because a single
    response of roughly twenty did not validate, while the same prompt
    validated on every isolated repeat.
    """

    client, seen = structured_client("not json", '{"value": 7}')

    result = client.complete_structured([LLMMessage(role="user", content="hi")], _Shape)

    assert result.value == 7
    assert len(seen) == 2


def test_a_first_response_that_matches_is_not_asked_for_twice() -> None:
    client, seen = structured_client('{"value": 1}')

    client.complete_structured([LLMMessage(role="user", content="hi")], _Shape)

    assert len(seen) == 1, "a conforming response must cost one call"


def test_a_provider_that_never_conforms_still_fails() -> None:
    """Retrying must not turn an incapable provider into an infinite wait."""

    client, seen = structured_client("not json")

    with pytest.raises(LLMStructuredOutputError, match="in 2 attempts"):
        client.complete_structured([LLMMessage(role="user", content="hi")], _Shape)

    assert len(seen) == STRUCTURED_OUTPUT_ATTEMPTS


def test_the_original_validation_error_is_kept_as_the_cause() -> None:
    """A reader needs to know which field was wrong, not only that it failed."""

    client, _ = structured_client("not json")

    with pytest.raises(LLMStructuredOutputError) as raised:
        client.complete_structured([LLMMessage(role="user", content="hi")], _Shape)

    assert raised.value.__cause__ is not None


def test_the_request_is_repeated_unchanged() -> None:
    """Feeding the validation error back invites invented values.

    Invariant 1 makes a fabricated identifier worse than a failed call, so the
    retry asks the same question rather than describing what was wrong.
    """

    bodies: list[dict] = []

    def respond(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "not json"}}]}
        )

    client = OpenAICompatibleLLMClient(
        retry_backoff_seconds=0,
        base_url="https://provider.test/v1",
        api_key="secret",
        model="m",
        transport=httpx.MockTransport(respond),
    )
    with pytest.raises(LLMStructuredOutputError):
        client.complete_structured([LLMMessage(role="user", content="hi")], _Shape)

    assert len(bodies) == 2
    assert bodies[0]["messages"] == bodies[1]["messages"]


def test_a_mocked_client_is_never_asked_twice() -> None:
    """The deterministic path has nothing to re-roll."""

    calls = {"n": 0}

    def factory() -> _Shape:
        calls["n"] += 1
        return _Shape(value=3)

    result = MockLLMClient().complete_structured(
        [LLMMessage(role="user", content="hi")], _Shape, mock_factory=factory
    )

    assert result.value == 3
    assert calls["n"] == 1


def provider_returning(
    content: str, *, finish_reason: str | None = "stop", **client_kwargs: object
) -> tuple[OpenAICompatibleLLMClient, list[dict]]:
    """A client whose provider always answers the same way."""

    seen: list[dict] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": content}, "finish_reason": finish_reason}
                ]
            },
        )

    client = OpenAICompatibleLLMClient(
        retry_backoff_seconds=0,
        base_url="https://provider.test/v1",
        api_key="secret",
        model="m",
        transport=httpx.MockTransport(respond),
        **client_kwargs,
    )
    return client, seen


def test_a_truncated_answer_is_named_rather_than_blamed_on_the_schema() -> None:
    """The message must point at the output limit, not at the contract.

    A truncated response used to reach JSON parsing and fail there, so an
    output ceiling was reported as "the response did not match the contract" —
    which sends an investigation toward the schema.
    """

    client, _ = provider_returning('{"value": 1', finish_reason="length")

    with pytest.raises(LLMResponseTruncatedError, match="stopped before finishing"):
        client.complete_structured([LLMMessage(role="user", content="hi")], _Shape)


def test_a_truncated_answer_is_not_asked_for_again() -> None:
    """Retrying reproduces the same length and truncates in the same place."""

    client, seen = provider_returning('{"value": 1', finish_reason="length")

    with pytest.raises(LLMResponseTruncatedError):
        client.complete_structured([LLMMessage(role="user", content="hi")], _Shape)

    assert len(seen) == 1, "a second attempt would only waste the same budget"


def test_truncation_is_caught_on_plain_completions_too() -> None:
    client, _ = provider_returning("half a sen", finish_reason="length")

    with pytest.raises(LLMResponseTruncatedError):
        client.complete([LLMMessage(role="user", content="hi")])


def test_a_finished_answer_is_returned_normally() -> None:
    client, _ = provider_returning('{"value": 4}', finish_reason="stop")

    assert (
        client.complete_structured(
            [LLMMessage(role="user", content="hi")], _Shape
        ).value
        == 4
    )


def test_a_provider_that_reports_no_finish_reason_is_trusted() -> None:
    """Not every OpenAI-compatible provider sends the field."""

    client, _ = provider_returning('{"value": 5}', finish_reason=None)

    assert (
        client.complete_structured(
            [LLMMessage(role="user", content="hi")], _Shape
        ).value
        == 5
    )


def test_no_output_ceiling_is_sent_unless_one_is_configured() -> None:
    """Leaving it unset must not change what a working provider receives."""

    client, seen = provider_returning('{"value": 1}')

    client.complete_structured([LLMMessage(role="user", content="hi")], _Shape)

    assert "max_tokens" not in seen[0]


def test_a_configured_output_ceiling_reaches_the_provider() -> None:
    client, seen = provider_returning('{"value": 1}', max_output_tokens=8192)

    client.complete_structured([LLMMessage(role="user", content="hi")], _Shape)

    assert seen[0]["max_tokens"] == 8192


def test_the_configured_ceiling_comes_from_settings() -> None:
    settings = Settings(
        mock_llm=False,
        llm_base_url="https://provider.test/v1",
        llm_api_key="secret",
        llm_model="m",
        llm_max_output_tokens=8192,
    )

    client = get_llm_client(settings)

    assert isinstance(client, OpenAICompatibleLLMClient)
    assert client._max_output_tokens == 8192


def _backoff_client(**overrides: object) -> OpenAICompatibleLLMClient:
    return OpenAICompatibleLLMClient(
        base_url="https://example.test/v1",
        api_key="sk-test",
        model="test-model",
        **overrides,  # type: ignore[arg-type]
    )


def test_each_retry_waits_longer_than_the_last() -> None:
    """Retries spaced evenly land back inside the window that refused them."""

    client = _backoff_client(retry_backoff_seconds=4.0)

    delays = [client._retry_delay(attempt, None) for attempt in range(3)]

    assert delays == [4.0, 8.0, 16.0]


def test_a_provider_that_says_when_to_return_is_believed() -> None:
    """Retry-After comes from the side that knows when the window reopens."""

    client = _backoff_client(retry_backoff_seconds=4.0)
    response = httpx.Response(429, headers={"Retry-After": "7"})

    assert client._retry_delay(0, response) == 7.0


def test_an_unreadable_retry_after_falls_back_to_the_computed_wait() -> None:
    """The HTTP-date form is not parsed; a wrong clock would wait wrongly."""

    client = _backoff_client(retry_backoff_seconds=4.0)
    response = httpx.Response(
        429, headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}
    )

    assert client._retry_delay(0, response) == 4.0


def test_the_wait_is_capped_so_a_run_cannot_stall_indefinitely() -> None:
    client = _backoff_client(retry_backoff_seconds=4.0)
    response = httpx.Response(429, headers={"Retry-After": "9000"})

    assert client._retry_delay(9, None) == RETRY_BACKOFF_MAX_SECONDS
    assert client._retry_delay(0, response) == RETRY_BACKOFF_MAX_SECONDS
