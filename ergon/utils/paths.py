from __future__ import annotations

from pathlib import Path


def find_project_root(start: Path | None = None) -> Path | None:
    """Walk upward from `start` looking for a project-local `.ergon/project.yaml`.

    This deliberately ignores the global `~/.ergon/` config directory so
    commands run inside arbitrary repos do not accidentally latch onto the
    user's home directory as the project root.
    """
    cur = (start or Path.cwd()).resolve()
    for candidate in [cur, *cur.parents]:
        if (candidate / ".ergon" / "project.yaml").is_file():
            return candidate
    return None


def ergon_dir(project_root: Path) -> Path:
    return project_root / ".ergon"


def tasks_dir(project_root: Path) -> Path:
    return ergon_dir(project_root) / "tasks"


def runs_dir(project_root: Path) -> Path:
    return ergon_dir(project_root) / "runs"


def logs_dir(project_root: Path) -> Path:
    return ergon_dir(project_root) / "logs"


def memory_dir(project_root: Path) -> Path:
    return ergon_dir(project_root) / "memory"


def project_yaml_path(project_root: Path) -> Path:
    return ergon_dir(project_root) / "project.yaml"


def global_config_dir() -> Path:
    return Path.home() / ".ergon"


def agents_yaml_path() -> Path:
    return global_config_dir() / "agents.yaml"


def worktrees_root() -> Path:
    return Path.home() / "ergon" / "worktrees"
