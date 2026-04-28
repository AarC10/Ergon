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
ProjectType = Literal[
    "embedded-zephyr",
    "roblox-rojo",
    "ros2",
    "python",
    "generic",
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


class AgentDef(BaseModel):
    backend: Literal["cli", "api"] = "cli"
    command: str
    default_role: str | None = None
    mode: Literal["native", "controlled", "unsafe", "unrestricted"] = "controlled"
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)


class AgentsConfig(BaseModel):
    agents: dict[str, AgentDef] = Field(default_factory=dict)

    @classmethod
    def load(cls) -> "AgentsConfig":
        path = agents_yaml_path()
        if not path.exists():
            return cls(agents=cls.default_agents())
        return cls.model_validate(load_yaml(path))

    def save(self) -> None:
        dump_yaml(agents_yaml_path(), self.model_dump())

    @staticmethod
    def default_agents() -> dict[str, AgentDef]:
        return {
            "claude": AgentDef(
                backend="cli",
                command="claude",
                default_role="implementer",
                mode="native",
            ),
            "openai": AgentDef(
                backend="cli",
                command="codex",
                default_role="planner_reviewer_debugger",
                mode="controlled",
            ),
            "gemini": AgentDef(
                backend="cli",
                command="gemini",
                default_role="analyzer_reviewer",
                mode="controlled",
            ),
        }


class TaskScope(BaseModel):
    allowed_paths: list[str] = Field(default_factory=list)
    forbidden_paths: list[str] = Field(default_factory=lambda: [".git/**"])


class TaskConfig(BaseModel):
    id: str  # zero-padded numeric id, e.g. "001"
    title: str
    slug: str
    status: Literal[
        "draft",
        "planning",
        "ready",
        "implementing",
        "validating",
        "reviewing",
        "blocked",
        "completed",
        "abandoned",
    ] = "draft"
    repo: str
    base_branch: str = "main"
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    goal: str = ""
    type: Literal[
        "feature",
        "bugfix",
        "refactor",
        "analysis",
        "debug",
        "docs",
        "chore",
    ] = "feature"

    scope: TaskScope = Field(default_factory=TaskScope)
    constraints: list[str] = Field(default_factory=list)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    agents: ProjectAgents = Field(default_factory=ProjectAgents)

    manual_gate: bool = True
    safety_level: SafetyLevel = "guarded"

    worktree_path: str | None = None
    branch_name: str | None = None
