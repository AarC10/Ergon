from __future__ import annotations

from ergon.agents.base import Agent
from ergon.agents.cli_agent import CliAgent
from ergon.core.config import AgentsConfig


class AgentRegistry:
    def __init__(self, config: AgentsConfig | None = None):
        self.config = config or AgentsConfig.load()

    def get(self, name: str) -> Agent:
        if name not in self.config.agents:
            available = ", ".join(self.config.agents) or "(none configured)"
            raise KeyError(
                f"Unknown agent '{name}'. Configured agents: {available}. "
                f"Edit ~/.ergon/agents.yaml to add it."
            )
        definition = self.config.agents[name]
        return CliAgent(name=name, definition=definition)

    def names(self) -> list[str]:
        return list(self.config.agents.keys())
