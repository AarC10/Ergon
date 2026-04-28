from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from ergon.core.config import (
    AgentsConfig,
    ContextConfig,
    ProjectAgents,
    ProjectConfig,
    RulesConfig,
    SafetyLevel,
    ValidationConfig,
)
from ergon.utils.paths import (
    agents_yaml_path,
    ergon_dir,
    logs_dir,
    memory_dir,
    runs_dir,
    tasks_dir,
)


_DEFAULT_INCLUDE = ["README.md", "src/**", "include/**", "tests/**", "docs/**"]
_DEFAULT_EXCLUDE = ["build/**", ".git/**", ".venv/**", "node_modules/**"]


_TYPE_DEFAULTS: dict[str, dict] = {
    "embedded-zephyr": {
        "validation": ["west build -b <board> app", "west twister -T tests"],
        "safety": "strict",
        "include": ["README.md", "app/**", "src/**", "include/**", "tests/**", "docs/**"],
    },
    "roblox-rojo": {
        "validation": ["rojo build -o build.rbxlx"],
        "safety": "guarded",
        "include": ["README.md", "src/**", "shared/**", "server/**", "client/**"],
    },
    "ros2": {
        "validation": ["colcon build", "colcon test"],
        "safety": "guarded",
        "include": ["README.md", "src/**", "launch/**", "config/**"],
    },
    "python": {
        "validation": ["python -m pytest"],
        "safety": "guarded",
        "include": ["README.md", "src/**", "tests/**"],
    },
    "generic": {
        "validation": [],
        "safety": "guarded",
        "include": _DEFAULT_INCLUDE,
    },
}


_MEMORY_FILES = {
    "architecture.md": dedent(
        """\
        # Architecture

        High-level structure of this project. Update as the project evolves.

        ## Components

        ## Data flow

        ## External dependencies
        """
    ),
    "decisions.md": dedent(
        """\
        # Decisions

        Architectural / engineering decisions and the reasons behind them.
        Format: `YYYY-MM-DD — Decision — Why`.
        """
    ),
    "conventions.md": dedent(
        """\
        # Conventions

        Coding style, naming, commit message style, branching, review style.
        """
    ),
    "glossary.md": dedent(
        """\
        # Glossary

        Project-specific terms, abbreviations, and acronyms.
        """
    ),
}


def init_project(
    repo_path: Path,
    name: str,
    project_type: str = "generic",
    force: bool = False,
) -> ProjectConfig:
    """Create the .ergon/ scaffold under repo_path."""
    defaults = _TYPE_DEFAULTS.get(project_type, _TYPE_DEFAULTS["generic"])

    edir = ergon_dir(repo_path)
    edir.mkdir(parents=True, exist_ok=True)
    tasks_dir(repo_path).mkdir(parents=True, exist_ok=True)
    runs_dir(repo_path).mkdir(parents=True, exist_ok=True)
    logs_dir(repo_path).mkdir(parents=True, exist_ok=True)
    mdir = memory_dir(repo_path)
    mdir.mkdir(parents=True, exist_ok=True)

    for fname, body in _MEMORY_FILES.items():
        target = mdir / fname
        if not target.exists():
            target.write_text(body, encoding="utf-8")

    safety: SafetyLevel = defaults["safety"]
    config = ProjectConfig(
        name=name,
        type=project_type if project_type in _TYPE_DEFAULTS else "generic",  # type: ignore[arg-type]
        repo_path=str(repo_path),
        default_branch=_detect_default_branch(repo_path),
        validation=ValidationConfig(commands=list(defaults["validation"])),
        rules=RulesConfig(safety_level=safety),
        agents=ProjectAgents(
            planner="openai",
            implementer="claude",
            debugger="openai",
            analyzer="gemini",
            reviewers=["openai", "gemini"],
        ),
        context=ContextConfig(
            include=list(defaults["include"]),
            exclude=list(_DEFAULT_EXCLUDE),
        ),
    )
    config.save(repo_path)

    # Ensure global agents.yaml exists with defaults.
    if not agents_yaml_path().exists():
        AgentsConfig(agents=AgentsConfig.default_agents()).save()

    # gitignore the volatile parts of .ergon/.
    _ensure_gitignore(edir)
    return config


def _detect_default_branch(repo_path: Path) -> str:
    head = repo_path / ".git" / "HEAD"
    if head.exists():
        try:
            content = head.read_text(encoding="utf-8").strip()
            if content.startswith("ref:"):
                return content.split("/")[-1]
        except OSError:
            pass
    return "main"


def _ensure_gitignore(edir: Path) -> None:
    gi = edir / ".gitignore"
    if gi.exists():
        return
    gi.write_text(
        dedent(
            """\
            # Volatile Ergon state — keep tasks/ and memory/ committed.
            runs/
            logs/
            """
        ),
        encoding="utf-8",
    )
