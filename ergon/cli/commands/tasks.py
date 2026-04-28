from __future__ import annotations

import re

import typer
from rich.table import Table

from ergon.core.artifact_store import TaskArtifacts
from ergon.core.project import Project, ProjectNotInitialized
from ergon.ui.console import console, error, warn


_TASK_DIR_RE = re.compile(r"^(\d{3,})-(.+)$")


def run() -> None:
    """List tasks in the current project."""
    try:
        project = Project.discover()
    except ProjectNotInitialized as e:
        error(str(e))
        raise typer.Exit(code=1) from e

    if not project.tasks_dir.exists():
        warn("No tasks yet. Use `ergon start <title>`.")
        return

    folders = sorted(p for p in project.tasks_dir.iterdir() if p.is_dir())
    if not folders:
        warn("No tasks yet. Use `ergon start <title>`.")
        return

    table = Table(title=f"Tasks in {project.config.name}", show_lines=False)
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Status", style="magenta")
    table.add_column("Type")
    table.add_column("Title")
    table.add_column("Worktree", overflow="fold")
    for folder in folders:
        if not _TASK_DIR_RE.match(folder.name):
            continue
        try:
            task = TaskArtifacts(root=folder).load_task()
        except (FileNotFoundError, ValueError):
            continue
        wt = task.worktree_path or "-"
        table.add_row(task.id, task.status, task.type, task.title, wt)
    console.print(table)
