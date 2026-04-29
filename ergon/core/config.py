from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from ergon.utils.paths import (
    agents_yaml_path,
    project_yaml_path,
)
from ergon.utils.yaml import dump_yaml, load_yaml


SafetyLevel = Literal["strict", "guarded", "unsafe", "unrestricted"]
SAFETY_LEVELS: tuple[str, ...] = ("strict", "guarded", "unsafe", "unrestricted")

ProjectType = Literal[
    "embedded-zephyr",
    "roblox-rojo",
    "ros2",
    "python",
    "generic",
]

TaskType = Literal[
    "feature",
    "bugfix",
    "refactor",
    "analysis",
    "debug",
    "docs",
    "chore",
]
TASK_TYPES: tuple[str, ...] = (
    "feature",
    "bugfix",
    "refactor",
    "analysis",
    "debug",
    "docs",
    "chore",
)


ROLE_NAMES: tuple[str, ...] = (
    "planner",
    "architect",
    "implementer",
    "large_refactor",
    "debugger",
    "reviewer_correctness",
    "reviewer_code_quality",
    "analyzer",
    "analyzer_multimodal",
    "summarizer",
)
REVIEWER_ROLE_NAMES: tuple[str, ...] = (
    "reviewer_correctness",
    "reviewer_code_quality",
)


# Task lifecycle. Each "*ing" status has a paired terminal state ("*ed" /
# planned / validated / reviewed). "failed" is reached when a step errors
# before producing usable output. "blocked" / "abandoned" are manual.
TaskStatus = Literal[
    "created",
    "planning",
    "planned",
    "implementing",
    "implemented",
    "validating",
    "validated",
    "reviewing",
    "reviewed",
    "failed",
    "blocked",
    "abandoned",
]


class CommandSpec(BaseModel):
    command: str
    timeout_sec: int = 600


class ValidationConfig(BaseModel):
    commands: list[str] = Field(default_factory=list)


class RulesConfig(BaseModel):
    auto_merge: bool = False
    auto_push: bool = False
    require_manual_approval: bool = True
    safety_level: SafetyLevel = "guarded"


class ProjectAgents(BaseModel):
    planner: str | None = None
    implementer: str | None = None
    debugger: str | None = None
    analyzer: str | None = None
    reviewers: list[str] = Field(default_factory=list)


class RoleRoute(BaseModel):
    primary: str | None = None
    fallback: str | None = None
    escalation: str | None = None


class ContextConfig(BaseModel):
    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)


class ProjectConfig(BaseModel):
    name: str
    type: ProjectType = "generic"
    repo_path: str
    default_branch: str = "main"

    build: CommandSpec | None = None
    test: CommandSpec | None = None

    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    rules: RulesConfig = Field(default_factory=RulesConfig)
    agents: ProjectAgents = Field(default_factory=ProjectAgents)
    roles: dict[str, RoleRoute] = Field(default_factory=dict)
    context: ContextConfig = Field(default_factory=ContextConfig)

    @classmethod
    def load(cls, project_root: Path) -> "ProjectConfig":
        path = project_yaml_path(project_root)
        if not path.exists():
            raise FileNotFoundError(
                f"No project config at {path}. Run `ergon init` first."
            )
        return cls.model_validate(load_yaml(path))

    def save(self, project_root: Path) -> None:
        dump_yaml(project_yaml_path(project_root), self.model_dump(exclude_none=True))


class AgentEnv(BaseModel):
    """Per-agent environment policy.

    Agent subprocesses run with a minimal allowlisted environment by default
    (see `agents/cli_agent.py`). `passthrough` names additional parent-env
    variables to forward (e.g. ANTHROPIC_API_KEY). `set` adds explicit
    key-value pairs which override anything inherited.
    """

    passthrough: list[str] = Field(default_factory=list)
    set: dict[str, str] = Field(default_factory=dict)


class AgentDef(BaseModel):
    backend: Literal["cli", "api"] = "cli"
    command: str
    model: str | None = None
    invocation: str | None = None
    default_role: str | None = None
    mode: Literal["native", "controlled", "unsafe", "unrestricted"] = "controlled"
    args: list[str] = Field(default_factory=list)
    env: AgentEnv = Field(default_factory=AgentEnv)


class AgentsConfig(BaseModel):
    agents: dict[str, AgentDef] = Field(default_factory=dict)
    roles: dict[str, RoleRoute] = Field(default_factory=dict)

    @classmethod
    def load(cls) -> "AgentsConfig":
        path = agents_yaml_path()
        if not path.exists():
            return cls(agents=cls.default_agents(), roles={})
        data = load_yaml(path)
        defaults = cls.default_agents()
        merged_agents: dict[str, object] = {}
        raw_agents = data.get("agents") or {}
        for name, default in defaults.items():
            override = raw_agents.get(name)
            if isinstance(override, AgentDef):
                merged_agents[name] = {
                    **default.model_dump(exclude_none=True),
                    **override.model_dump(exclude_none=True),
                }
            elif isinstance(override, dict):
                merged_agents[name] = {
                    **default.model_dump(exclude_none=True),
                    **override,
                }
            else:
                merged_agents[name] = default
        for name, override in raw_agents.items():
            if name not in merged_agents:
                merged_agents[name] = override
        merged = dict(data)
        merged["agents"] = merged_agents
        merged.setdefault("roles", {})
        return cls.model_validate(merged)

    def save(self) -> None:
        dump_yaml(agents_yaml_path(), self.model_dump())

    @staticmethod
    def default_agents() -> dict[str, AgentDef]:
        return {
            "gpt-5.5": AgentDef(
                backend="cli",
                command="codex",
                model="gpt-5.5",
                invocation="codex_exec",
                default_role="planner",
                mode="controlled",
                env=AgentEnv(
                    passthrough=[
                        "OPENAI_API_KEY",
                        "OPENAI_BASE_URL",
                        "CODEX_HOME",
                    ]
                ),
            ),
            "gpt-5.5-codex": AgentDef(
                backend="cli",
                command="codex",
                model="gpt-5.5",
                invocation="codex_exec",
                default_role="implementer",
                mode="controlled",
                env=AgentEnv(
                    passthrough=[
                        "OPENAI_API_KEY",
                        "OPENAI_BASE_URL",
                        "CODEX_HOME",
                    ]
                ),
            ),
            "sonnet-4.6": AgentDef(
                backend="cli",
                command="claude",
                model="sonnet-4.6",
                invocation="claude_print",
                default_role="implementer",
                mode="native",
                env=AgentEnv(
                    passthrough=[
                        "ANTHROPIC_API_KEY",
                        "CLAUDE_CONFIG_DIR",
                    ]
                ),
            ),
            "opus-4.7": AgentDef(
                backend="cli",
                command="claude",
                model="opus-4.7",
                invocation="claude_print",
                default_role="architect",
                mode="native",
                env=AgentEnv(
                    passthrough=[
                        "ANTHROPIC_API_KEY",
                        "CLAUDE_CONFIG_DIR",
                    ]
                ),
            ),
            "haiku-4.5": AgentDef(
                backend="cli",
                command="claude",
                model="haiku-4.5",
                invocation="claude_print",
                default_role="summarizer",
                mode="native",
                env=AgentEnv(
                    passthrough=[
                        "ANTHROPIC_API_KEY",
                        "CLAUDE_CONFIG_DIR",
                    ]
                ),
            ),
            "gemini-3-pro": AgentDef(
                backend="cli",
                command="gemini",
                model="gemini-3-pro",
                invocation="gemini_prompt",
                default_role="analyzer_multimodal",
                mode="controlled",
                env=AgentEnv(
                    passthrough=[
                        "GOOGLE_API_KEY",
                        "GEMINI_API_KEY",
                    ]
                ),
            ),
            "gemini-flash": AgentDef(
                backend="cli",
                command="gemini",
                model="gemini-flash",
                invocation="gemini_prompt",
                default_role="summarizer",
                mode="controlled",
                env=AgentEnv(
                    passthrough=[
                        "GOOGLE_API_KEY",
                        "GEMINI_API_KEY",
                    ]
                ),
            ),
            "claude": AgentDef(
                backend="cli",
                command="claude",
                invocation="claude_print",
                default_role="implementer",
                mode="native",
                env=AgentEnv(
                    passthrough=[
                        "ANTHROPIC_API_KEY",
                        "CLAUDE_CONFIG_DIR",
                    ]
                ),
            ),
            "openai": AgentDef(
                backend="cli",
                command="codex",
                invocation="codex_exec",
                default_role="planner_reviewer_debugger",
                mode="controlled",
                env=AgentEnv(
                    passthrough=[
                        "OPENAI_API_KEY",
                        "OPENAI_BASE_URL",
                        "CODEX_HOME",
                    ]
                ),
            ),
            "gemini": AgentDef(
                backend="cli",
                command="gemini",
                invocation="gemini_prompt",
                default_role="analyzer_reviewer",
                mode="controlled",
                env=AgentEnv(
                    passthrough=[
                        "GOOGLE_API_KEY",
                        "GEMINI_API_KEY",
                    ]
                ),
            ),
            "codex": AgentDef(
                backend="cli",
                command="codex",
                invocation="codex_exec",
                default_role="planner_reviewer_debugger",
                mode="controlled",
                env=AgentEnv(
                    passthrough=[
                        "OPENAI_API_KEY",
                        "OPENAI_BASE_URL",
                        "CODEX_HOME",
                    ]
                ),
            ),
        }

    @staticmethod
    def default_roles() -> dict[str, RoleRoute]:
        return {
            "planner": RoleRoute(primary="gpt-5.5", fallback="opus-4.7"),
            "architect": RoleRoute(primary="gpt-5.5", fallback="opus-4.7"),
            "implementer": RoleRoute(
                primary="sonnet-4.6",
                fallback="gpt-5.5-codex",
                escalation="opus-4.7",
            ),
            "large_refactor": RoleRoute(
                primary="opus-4.7",
                fallback="gpt-5.5-codex",
            ),
            "debugger": RoleRoute(primary="gpt-5.5", fallback="opus-4.7"),
            "reviewer_correctness": RoleRoute(
                primary="gpt-5.5",
                fallback="opus-4.7",
            ),
            "reviewer_code_quality": RoleRoute(
                primary="sonnet-4.6",
                fallback="gpt-5.5",
            ),
            "analyzer": RoleRoute(
                primary="gpt-5.5",
                fallback="gemini-3-pro",
            ),
            "analyzer_multimodal": RoleRoute(
                primary="gemini-3-pro",
                fallback="gpt-5.5",
            ),
            "summarizer": RoleRoute(
                primary="haiku-4.5",
                fallback="gemini-flash",
            ),
        }


class TaskScope(BaseModel):
    allowed_paths: list[str] = Field(default_factory=list)
    forbidden_paths: list[str] = Field(default_factory=lambda: [".git/**"])


class TaskConfig(BaseModel):
    id: str  # zero-padded numeric id, e.g. "001"
    title: str
    slug: str
    status: TaskStatus = "created"
    repo: str
    base_branch: str = "main"
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    goal: str = ""
    type: TaskType = "feature"

    scope: TaskScope = Field(default_factory=TaskScope)
    constraints: list[str] = Field(default_factory=list)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    agents: ProjectAgents = Field(default_factory=ProjectAgents)
    roles: dict[str, RoleRoute] = Field(default_factory=dict)

    manual_gate: bool = True
    safety_level: SafetyLevel = "guarded"

    worktree_path: str | None = None
    branch_name: str | None = None
