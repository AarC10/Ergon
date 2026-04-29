from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from ergon.core.config import AgentDef


class AgentNotAvailable(RuntimeError):
    pass


class AgentExecutionError(RuntimeError):
    pass


@dataclass
class AgentInvocation:
    agent_name: str
    role: str  # planner | implementer | reviewer | analyzer | debugger | summarizer
    cwd: Path
    prompt: str
    log_path: Path
    started_at: datetime
    finished_at: datetime | None = None
    exit_code: int | None = None
    output: str = ""


class Agent(Protocol):
    name: str
    definition: AgentDef

    def run_native(self, invocation: AgentInvocation) -> AgentInvocation: ...
    def run_controlled(self, invocation: AgentInvocation) -> AgentInvocation: ...


def assert_command_available(definition: AgentDef) -> None:
    if shutil.which(definition.command) is None:
        raise AgentNotAvailable(
            f"Required CLI '{definition.command}' was not found on PATH. "
            f"Install it or update ~/.ergon/agents.yaml."
        )
