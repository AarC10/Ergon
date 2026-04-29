from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from ergon.core.config import (
    AgentsConfig,
    ContextConfig,
    ProjectAgents,
    ProjectConfig,
    RoleRoute,
    RulesConfig,
    SafetyLevel,
    ValidationConfig,
)
from ergon.tools.git import NotAGitRepo, common_toplevel, git_common_dir, run_git
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


PROJECT_TYPES = tuple(_TYPE_DEFAULTS.keys())


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
    """Create the .ergon/ scaffold under repo_path.

    `repo_path` must be inside a git repository (main or linked worktree).
    """
    if project_type not in _TYPE_DEFAULTS:
        raise ValueError(
            f"Unknown project type '{project_type}'. "
            f"Choose one of: {', '.join(_TYPE_DEFAULTS)}"
        )
    defaults = _TYPE_DEFAULTS[project_type]

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
        type=project_type,  # type: ignore[arg-type]
        repo_path=str(repo_path),
        default_branch=_detect_default_branch(repo_path),
        validation=ValidationConfig(commands=list(defaults["validation"])),
        rules=RulesConfig(safety_level=safety),
        agents=ProjectAgents(
            planner="gpt-5.5",
            implementer="sonnet-4.6",
            debugger="gpt-5.5",
            analyzer="gemini-3-pro",
            reviewers=["gpt-5.5", "sonnet-4.6"],
        ),
        roles={k: RoleRoute(**v.model_dump()) for k, v in AgentsConfig.default_roles().items()},
        context=ContextConfig(
            include=list(defaults["include"]),
            exclude=list(_DEFAULT_EXCLUDE),
        ),
    )
    config.save(repo_path)

    if not agents_yaml_path().exists():
        AgentsConfig(
            agents=AgentsConfig.default_agents(),
            roles=AgentsConfig.default_roles(),
        ).save()

    _ensure_gitignore(edir)
    # Ergon's per-task scaffold files (ERGON_TASK.md etc) belong in the
    # *common* git dir's info/exclude — the per-worktree info/exclude is not
    # consulted by ls-files / status. Use rev-parse rather than assuming
    # `.git` is a directory (linked worktrees have `.git` as a file).
    _ensure_repo_excludes(repo_path)
    return config


_SCAFFOLD_FILES = (
    "ERGON_TASK.md",
    "ERGON_CONTEXT.md",
    "ERGON_CONSTRAINTS.md",
    "ERGON_PROMPT.md",
)


def _ensure_repo_excludes(repo_path: Path) -> None:
    try:
        common = git_common_dir(repo_path)
    except NotAGitRepo:
        return
    info_dir = common / "info"
    info_dir.mkdir(parents=True, exist_ok=True)
    exclude_file = info_dir / "exclude"
    existing = exclude_file.read_text(encoding="utf-8") if exclude_file.exists() else ""
    additions = [name for name in _SCAFFOLD_FILES if name not in existing]
    if not additions:
        return
    with exclude_file.open("a", encoding="utf-8") as f:
        if existing and not existing.endswith("\n"):
            f.write("\n")
        f.write("# Ergon scaffold (written into per-task worktrees)\n")
        for name in additions:
            f.write(f"{name}\n")


def _detect_default_branch(repo_path: Path) -> str:
    """Return the symbolic-ref short name for HEAD, or 'main' as a fallback.

    Uses git rather than reading .git/HEAD directly; linked worktrees have
    `.git` as a file pointing at the per-worktree git dir, and the symbolic
    ref logic differs.
    """
    res = run_git(
        ["symbolic-ref", "--quiet", "--short", "HEAD"], repo_path, check=False
    )
    if res.returncode == 0 and res.stdout.strip():
        return res.stdout.strip()
    # Detached HEAD or unborn branch — fall back to common-dir's HEAD or 'main'.
    try:
        common = git_common_dir(repo_path)
    except NotAGitRepo:
        return "main"
    head_file = common / "HEAD"
    if head_file.exists():
        try:
            content = head_file.read_text(encoding="utf-8").strip()
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
