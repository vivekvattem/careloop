import json
from dataclasses import dataclass
from typing import Protocol, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import settings

OutputT = TypeVar("OutputT", bound=BaseModel)


class LLMProvider(Protocol):
    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_schema: type[OutputT],
    ) -> tuple[OutputT, int]: ...


@dataclass
class LLMGenerationError(Exception):
    category: str
    safe_message: str
    attempts: int


def strict_json_schema(response_schema: type[BaseModel]) -> dict:
    schema = response_schema.model_json_schema()

    def enforce(node: object) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" or "properties" in node:
                properties = node.get("properties", {})
                node["required"] = list(properties)
                node["additionalProperties"] = False
            for value in node.values():
                enforce(value)
        elif isinstance(node, list):
            for value in node:
                enforce(value)

    enforce(schema)
    return schema


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_schema: type[OutputT],
    ) -> tuple[OutputT, int]:
        if not self.api_key.strip():
            raise LLMGenerationError("missing_configuration", "LLM API key is not configured", 0)

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": response_schema.__name__,
                    "strict": True,
                    "schema": strict_json_schema(response_schema),
                },
            },
        }
        attempts = 0
        while attempts < 2:
            attempts += 1
            try:
                with httpx.Client(
                    timeout=httpx.Timeout(self.timeout_seconds), transport=self.transport
                ) as client:
                    response = client.post(
                        f"{self.base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json=payload,
                    )
            except httpx.TimeoutException as exc:
                if attempts < 2:
                    continue
                raise LLMGenerationError("timeout", "LLM request timed out", attempts) from exc
            except httpx.HTTPError as exc:
                raise LLMGenerationError("provider_failure", "LLM request failed", attempts) from exc

            category = self._http_error_category(response.status_code)
            if category is not None:
                retryable = category in {"rate_limit", "server_error"}
                if retryable and attempts < 2:
                    continue
                messages = {
                    "authentication": "LLM authentication failed",
                    "model_not_found": "Configured LLM model was not found",
                    "rate_limit": "LLM rate limit exceeded",
                    "server_error": "LLM provider server error",
                    "provider_failure": "LLM provider rejected the request",
                }
                raise LLMGenerationError(category, messages[category], attempts)

            try:
                content = response.json()["choices"][0]["message"]["content"]
                if not isinstance(content, str):
                    raise TypeError
                content = self._strip_code_fence(content)
                return response_schema.model_validate(json.loads(content)), attempts
            except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValidationError) as exc:
                raise LLMGenerationError(
                    "schema_failure", "LLM returned invalid structured output", attempts
                ) from exc

        raise AssertionError("bounded retry loop exhausted unexpectedly")

    @staticmethod
    def _http_error_category(status_code: int) -> str | None:
        if 200 <= status_code < 300:
            return None
        if status_code == 401:
            return "authentication"
        if status_code == 404:
            return "model_not_found"
        if status_code == 429:
            return "rate_limit"
        if status_code >= 500:
            return "server_error"
        return "provider_failure"

    @staticmethod
    def _strip_code_fence(content: str) -> str:
        stripped = content.strip()
        if stripped.startswith("```json") and stripped.endswith("```"):
            return stripped[7:-3].strip()
        if stripped.startswith("```") and stripped.endswith("```"):
            return stripped[3:-3].strip()
        return stripped


def configured_provider() -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        timeout_seconds=settings.llm_timeout_seconds,
    )
