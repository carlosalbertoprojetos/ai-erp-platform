from __future__ import annotations

from application.ports import AgentPort


class AgentRegistry:
    def __init__(self):
        self._agents: dict[str, AgentPort] = {}

    def register(self, agent: AgentPort) -> None:
        self._agents[agent.name] = agent

    def get(self, name: str) -> AgentPort:
        return self._agents[name]

    def all(self) -> dict[str, AgentPort]:
        return dict(self._agents)
