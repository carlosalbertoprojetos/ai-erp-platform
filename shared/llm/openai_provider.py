from __future__ import annotations

import os

from pydantic import BaseModel

from domain.exceptions import LLMGenerationError
from shared.llm.provider import LLMProvider, LLMRequest


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, model: str | None = None):
        self._model = model or os.getenv("COREFLOW_OPENAI_MODEL", "gpt-5-mini")
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from openai import AsyncOpenAI

            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise LLMGenerationError("OPENAI_API_KEY is required when provider='openai'.")
            self._client = AsyncOpenAI(api_key=api_key)
        return self._client

    async def generate_structured(self, request: LLMRequest, response_model: type[BaseModel]) -> BaseModel | dict | str:
        response = await self.client.responses.parse(
            model=request.model or self._model,
            instructions=request.instructions,
            input=request.prompt,
            text_format=response_model,
            temperature=request.temperature,
            reasoning={"effort": "minimal"},
            verbosity="low",
        )
        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise LLMGenerationError("OpenAI provider returned no parsed structured output.")
        return parsed
