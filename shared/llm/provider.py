from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class LLMRequest(BaseModel):
    instructions: str
    prompt: str
    temperature: float = 0.1
    model: str | None = None
    timeout_seconds: float = 30.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMProvider(ABC):
    name: str

    @abstractmethod
    async def generate_structured(self, request: LLMRequest, response_model: type[BaseModel]) -> BaseModel | dict | str:
        raise NotImplementedError
