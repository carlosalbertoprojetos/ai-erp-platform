from __future__ import annotations

import re

from domain.models import ArchitectureModule, ArchitecturePlan, EndpointSpec, FeatureRequest, UseCaseSpec


def slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower())
    return value.strip("_") or "coreflow_feature"


def pascalize(value: str) -> str:
    return "".join(part.capitalize() for part in slugify(value).split("_"))


class ArchitectureDomainService:
    def design(self, request: FeatureRequest) -> ArchitecturePlan:
        module_name = slugify(request.module_name or request.title)
        entity_name = pascalize(request.entities[0] if request.entities else f"{module_name}_record")
        capabilities = request.capabilities or [
            f"create_{module_name}",
            f"list_{module_name}",
            f"health_check_{module_name}",
        ]
        use_cases = [
            UseCaseSpec(
                name=pascalize(capability),
                description=f"Handle capability '{capability}' for feature '{request.title}'.",
            )
            for capability in capabilities
        ]
        endpoints = [
            EndpointSpec(
                method="POST",
                path=f"{request.api_prefix.rstrip('/')}/{module_name}",
                summary=f"Create a new {entity_name}",
                requires_auth=True,
            ),
            EndpointSpec(
                method="GET",
                path=f"{request.api_prefix.rstrip('/')}/{module_name}",
                summary=f"List {entity_name} entries",
                requires_auth=True,
            ),
        ]
        module = ArchitectureModule(
            name=module_name,
            description=f"Bounded context for {request.title}.",
            entities=[entity_name],
            use_cases=use_cases,
            endpoints=endpoints,
        )
        return ArchitecturePlan(
            feature=request,
            modules=[module],
            events=[f"{entity_name}Created"],
            policies=[
                "All public routes require bearer token authentication.",
                "All outputs must remain valid JSON.",
                "Business logic stays inside generated domain and application layers.",
            ],
        )
