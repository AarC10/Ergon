from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ergon.core.config import TaskConfig
from ergon.utils.yaml import dump_yaml, load_yaml


@dataclass
class TaskArtifacts:
    """Filesystem view of a task folder under .ergon/tasks/<id-slug>/."""

    root: Path

    @property
    def task_yaml(self) -> Path:
        return self.root / "task.yaml"

    @property
    def brief_md(self) -> Path:
        return self.root / "brief.md"

    @property
    def context_md(self) -> Path:
        return self.root / "context.md"

    @property
    def plan_md(self) -> Path:
        return self.root / "plan.md"

    @property
    def implementation_log(self) -> Path:
        return self.root / "implementation-log.md"

    @property
    def diff_patch(self) -> Path:
        return self.root / "diff.patch"

    @property
    def changed_files(self) -> Path:
        return self.root / "changed_files.txt"

    @property
    def validation_log(self) -> Path:
        return self.root / "validation.log"

    @property
    def review_summary(self) -> Path:
        return self.root / "review-summary.md"

    @property
    def final_md(self) -> Path:
        return self.root / "final.md"

    def review_for(self, agent: str) -> Path:
        return self.root / f"review-{agent}.md"

    def analyzer_for(self, agent: str) -> Path:
        return self.root / f"analyze-{agent}.md"

    def debug_for(self, agent: str) -> Path:
        return self.root / f"debug-{agent}.md"

    def write_text(self, name: str, body: str) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def append_text(self, name: str, body: str) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(body)
        return path

    def load_task(self) -> TaskConfig:
        return TaskConfig.model_validate(load_yaml(self.task_yaml))

    def save_task(self, task: TaskConfig) -> None:
        task.updated_at = datetime.now()
        dump_yaml(self.task_yaml, task.model_dump(mode="json", exclude_none=True))
