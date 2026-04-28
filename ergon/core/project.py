from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ergon.core.config import ProjectConfig
from ergon.utils.paths import (
    ergon_dir,
    find_project_root,
    logs_dir,
    memory_dir,
    runs_dir,
    tasks_dir,
)


class ProjectNotInitialized(RuntimeError):
    pass


@dataclass
class Project:
    root: Path
    config: ProjectConfig

    @property
    def ergon_dir(self) -> Path:
        return ergon_dir(self.root)

    @property
    def tasks_dir(self) -> Path:
        return tasks_dir(self.root)

    @property
    def runs_dir(self) -> Path:
        return runs_dir(self.root)

    @property
    def logs_dir(self) -> Path:
        return logs_dir(self.root)

    @property
    def memory_dir(self) -> Path:
        return memory_dir(self.root)

    @classmethod
    def discover(cls, start: Path | None = None) -> "Project":
        root = find_project_root(start)
        if root is None:
            raise ProjectNotInitialized(
                "No .ergon directory found. Run `ergon init` in a git repo."
            )
        return cls(root=root, config=ProjectConfig.load(root))
