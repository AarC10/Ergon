from __future__ import annotations

import typer

from ergon.core.config import TASK_TYPES
from ergon.core.project import Project, ProjectNotInitialized
from ergon.core.task import create_task
from ergon.ui.console import error, info, success


def run(
    title: str = typer.Argument(..., help="Short title for the new task"),
    type_: str = typer.Option(
        "feature",
        "--type",
        "-t",
        help=" | ".join(TASK_TYPES),
    ),
    goal: str | None = typer.Option(None, "--goal", "-g", help="Long-form goal"),
) -> None:
    """Create a new task from a short natural language title."""
    if type_ not in TASK_TYPES:
        error(
            f"Unknown --type '{type_}'. Choose one of: {', '.join(TASK_TYPES)}"
        )
        raise typer.Exit(code=2)

    try:
        project = Project.discover()
    except ProjectNotInitialized as e:
        error(str(e))
        raise typer.Exit(code=1) from e

    try:
        task, artifacts = create_task(project, title=title, type_=type_, goal=goal)
    except ValueError as e:
        error(str(e))
        raise typer.Exit(code=2) from e

    success(f"Created task {task.id}: {task.title}")
    info(f"Folder: {artifacts.root.relative_to(project.root)}")
    info("Edit brief.md to expand the task before planning or implementing.")
