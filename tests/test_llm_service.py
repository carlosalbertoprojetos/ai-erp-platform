from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from domain.exceptions import LLMGenerationError
from shared.llm.openai_provider import OpenAIProvider
from shared.llm.provider import LLMRequest
from shared.llm.service import StructuredLLMService
from shared.llm.template_provider import TemplateLLMProvider


class DemoPayload(BaseModel):
    value: str


class BrokenProvider:
    async def generate_structured(self, request, response_model):
        raise RuntimeError("bad")


class FencedJsonProvider:
    async def generate_structured(self, request, response_model):
        return "```json\n{\"value\": \"ok\"}\n```"


async def test_structured_llm_service_validates_template_output():
    service = StructuredLLMService(TemplateLLMProvider())
    result = await service.generate(
        LLMRequest(
            instructions="Return structured output.",
            prompt="demo",
            metadata={"template_output": {"value": "ok"}},
        ),
        DemoPayload,
    )

    assert result.value == "ok"


async def test_structured_llm_service_sanitizes_fenced_json():
    service = StructuredLLMService(FencedJsonProvider(), max_attempts=1)
    result = await service.generate(LLMRequest(instructions="demo", prompt="demo"), DemoPayload)

    assert result.value == "ok"


async def test_structured_llm_service_uses_fallback_on_failure():
    service = StructuredLLMService(BrokenProvider(), max_attempts=1)
    result = await service.generate(
        LLMRequest(instructions="demo", prompt="demo"),
        DemoPayload,
        fallback=DemoPayload(value="fallback"),
    )

    assert result.value == "fallback"


async def test_structured_llm_service_opens_circuit_breaker():
    service = StructuredLLMService(BrokenProvider(), max_attempts=1, circuit_breaker_threshold=1, circuit_breaker_cooldown_seconds=60)
    with pytest.raises(LLMGenerationError):
        await service.generate(LLMRequest(instructions="demo", prompt="demo"), DemoPayload)
    with pytest.raises(LLMGenerationError):
        await service.generate(LLMRequest(instructions="demo", prompt="demo"), DemoPayload)


async def test_openai_provider_returns_parsed_response():
    provider = OpenAIProvider(model="gpt-5-mini")

    class _FakeClient:
        class responses:
            @staticmethod
            async def parse(**kwargs):
                return SimpleNamespace(output_parsed=DemoPayload(value="ok"))

    provider._client = _FakeClient()
    result = await provider.generate_structured(LLMRequest(instructions="x", prompt="y"), DemoPayload)

    assert result.value == "ok"
