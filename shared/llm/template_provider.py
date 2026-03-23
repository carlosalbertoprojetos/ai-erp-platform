from __future__ import annotations

from pydantic import BaseModel

from domain.exceptions import LLMGenerationError
from shared.llm.provider import LLMProvider, LLMRequest


class TemplateLLMProvider(LLMProvider):
    name = "template"

    async def generate_structured(self, request: LLMRequest, response_model: type[BaseModel]) -> BaseModel | dict:
        template_output = request.metadata.get("template_output")
        if template_output is None:
            raise LLMGenerationError("Template provider requires metadata['template_output'].")
        return response_model.model_validate(template_output)
