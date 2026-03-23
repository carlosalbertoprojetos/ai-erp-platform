from __future__ import annotations

import asyncio
import json
import time

from pydantic import BaseModel

from domain.exceptions import LLMGenerationError
from shared.llm.provider import LLMRequest


class StructuredLLMService:
    def __init__(
        self,
        provider,
        max_attempts: int = 3,
        retry_delay_seconds: float = 0.25,
        request_timeout_seconds: float = 30.0,
        circuit_breaker_threshold: int = 3,
        circuit_breaker_cooldown_seconds: float = 30.0,
    ):
        self.provider = provider
        self.max_attempts = max_attempts
        self.retry_delay_seconds = retry_delay_seconds
        self.request_timeout_seconds = request_timeout_seconds
        self.circuit_breaker_threshold = circuit_breaker_threshold
        self.circuit_breaker_cooldown_seconds = circuit_breaker_cooldown_seconds
        self._failure_count = 0
        self._circuit_open_until = 0.0

    async def generate(
        self,
        request: LLMRequest,
        response_model: type[BaseModel],
        fallback: BaseModel | None = None,
    ) -> BaseModel:
        if self._circuit_open_until > time.monotonic():
            if fallback is not None:
                return fallback
            raise LLMGenerationError("LLM circuit breaker is open; refusing new requests until cooldown expires.")

        last_error: Exception | None = None
        timeout = request.timeout_seconds or self.request_timeout_seconds

        for attempt in range(1, self.max_attempts + 1):
            try:
                response = await asyncio.wait_for(
                    self.provider.generate_structured(request, response_model),
                    timeout=timeout,
                )
                validated = self._validate_response(response, response_model)
                self._failure_count = 0
                self._circuit_open_until = 0.0
                return validated
            except Exception as exc:
                last_error = exc
                self._failure_count += 1
                if self._failure_count >= self.circuit_breaker_threshold:
                    self._circuit_open_until = time.monotonic() + self.circuit_breaker_cooldown_seconds
                if attempt < self.max_attempts:
                    await asyncio.sleep(self.retry_delay_seconds * attempt)

        if fallback is not None:
            return fallback
        raise LLMGenerationError(f"Failed to generate structured output after retries: {last_error}") from last_error

    def _validate_response(self, response, response_model: type[BaseModel]) -> BaseModel:
        if isinstance(response, response_model):
            return response
        if isinstance(response, BaseModel):
            return response_model.model_validate(response.model_dump(mode="json"))
        if isinstance(response, str):
            return response_model.model_validate(json.loads(self._sanitize_text_response(response)))
        if isinstance(response, dict):
            return response_model.model_validate(response)
        raise LLMGenerationError(f"Unsupported provider response type: {type(response)!r}")

    def _sanitize_text_response(self, response: str) -> str:
        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
            cleaned = cleaned.rsplit("```", 1)[0]
        return cleaned.strip()
