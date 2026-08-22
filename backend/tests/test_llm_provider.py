import json

import httpx
import pytest

from app.core.config import settings
from app.schemas.visit import PreVisitLLMOutput
from app.services.llm import (
    LLMGenerationError,
    OpenAICompatibleProvider,
    strict_json_schema,
)


def valid_output() -> dict:
    return {
        "urgency": "Medium",
        "chief_complaint": "Headache",
        "suggested_questions": ["Question one?", "Question two?", "Question three?"],
        "relevant_history_note": None,
        "safety_disclaimer": "Clinician review required.",
    }


def test_documented_groq_defaults_remain_environment_configurable() -> None:
    assert settings.llm_provider == "openai_compatible"
    assert settings.llm_base_url == "https://api.groq.com/openai/v1"
    assert settings.llm_model == "openai/gpt-oss-20b"


def test_test_configuration_does_not_load_local_llm_api_key() -> None:
    assert settings.llm_api_key == ""


def test_groq_request_uses_strict_schema_and_pydantic_validation() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(valid_output())}}]},
        )

    provider = OpenAICompatibleProvider(
        api_key="test-key",
        base_url="https://api.groq.com/openai/v1",
        model="openai/gpt-oss-20b",
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )
    result, attempts = provider.generate_structured(
        system_prompt="system", user_prompt="user", response_schema=PreVisitLLMOutput
    )

    schema_config = captured["response_format"]["json_schema"]
    assert captured["model"] == "openai/gpt-oss-20b"
    assert captured["response_format"]["type"] == "json_schema"
    assert schema_config["strict"] is True
    assert schema_config["schema"]["additionalProperties"] is False
    assert set(schema_config["schema"]["required"]) == set(
        schema_config["schema"]["properties"]
    )
    assert result.urgency.value == "Medium"
    assert attempts == 1


@pytest.mark.parametrize(
    "status_code,category,expected_calls",
    [
        (404, "model_not_found", 1),
        (429, "rate_limit", 2),
        (503, "server_error", 2),
    ],
)
def test_provider_error_categories_and_bounded_retries(
    status_code: int, category: str, expected_calls: int
) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status_code)

    provider = OpenAICompatibleProvider(
        api_key="test-key",
        base_url="https://example.invalid/v1",
        model="test-model",
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(LLMGenerationError) as raised:
        provider.generate_structured(
            system_prompt="system", user_prompt="user", response_schema=PreVisitLLMOutput
        )
    assert raised.value.category == category
    assert raised.value.attempts == expected_calls
    assert calls == expected_calls


def test_authentication_failure_uses_mocked_401_and_is_not_retried() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401)

    provider = OpenAICompatibleProvider(
        api_key="test-key",
        base_url="https://example.invalid/v1",
        model="test-model",
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(LLMGenerationError) as raised:
        provider.generate_structured(
            system_prompt="system", user_prompt="user", response_schema=PreVisitLLMOutput
        )
    assert raised.value.category == "authentication"
    assert raised.value.attempts == 1
    assert calls == 1


def test_timeout_retries_once_and_malformed_or_invalid_schema_does_not_retry() -> None:
    timeout_calls = 0

    def timeout(_: httpx.Request) -> httpx.Response:
        nonlocal timeout_calls
        timeout_calls += 1
        raise httpx.ReadTimeout("timed out")

    timeout_provider = OpenAICompatibleProvider(
        api_key="key", base_url="https://example.invalid", model="model", timeout_seconds=1,
        transport=httpx.MockTransport(timeout),
    )
    with pytest.raises(LLMGenerationError) as timeout_error:
        timeout_provider.generate_structured(
            system_prompt="system", user_prompt="user", response_schema=PreVisitLLMOutput
        )
    assert timeout_error.value.category == "timeout"
    assert timeout_calls == 2

    for content in (
        "not-json",
        json.dumps(valid_output() | {"urgency": "Critical"}),
        json.dumps(valid_output() | {"suggested_questions": ["Only one?"]}),
    ):
        calls = 0

        def invalid(_: httpx.Request, value=content) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json={"choices": [{"message": {"content": value}}]})

        provider = OpenAICompatibleProvider(
            api_key="key", base_url="https://example.invalid", model="model", timeout_seconds=1,
            transport=httpx.MockTransport(invalid),
        )
        with pytest.raises(LLMGenerationError) as invalid_error:
            provider.generate_structured(
                system_prompt="system", user_prompt="user", response_schema=PreVisitLLMOutput
            )
        assert invalid_error.value.category == "schema_failure"
        assert calls == 1


def test_missing_configuration_is_immediate_fallback_category() -> None:
    provider = OpenAICompatibleProvider(
        api_key="", base_url="https://api.groq.com/openai/v1", model="model", timeout_seconds=1
    )
    with pytest.raises(LLMGenerationError) as raised:
        provider.generate_structured(
            system_prompt="system", user_prompt="user", response_schema=PreVisitLLMOutput
        )
    assert raised.value.category == "missing_configuration"
    assert raised.value.attempts == 0
