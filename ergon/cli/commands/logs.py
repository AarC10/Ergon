from __future__ import annotations

import typer

from ergon.core.project import Project, ProjectNotInitialized
from ergon.core.task import load_task
from ergon.ui.console import console, error, info, warn


def run(
    task_id: str = typer.Argument(..., help="Task id"),
    artifact: str | None = typer.Option(
        None, "--file", "-f", help="Specific artifact to print (e.g. plan.md)"
    ),
) -> None:
    """Show task logs / artifact contents."""
    try:
        project = Project.discover()
    except ProjectNotInitialized as e:
        error(str(e))
        raise typer.Exit(code=1) from e

    try:
        _, artifacts = load_task(project, task_id)
    except FileNotFoundError as e:
        error(str(e))
        raise typer.Exit(code=1) from e

    if artifact:
        path = artifacts.root / artifact
        if not path.exists():
            error(f"No artifact: {path.relative_to(project.root)}")
            raise typer.Exit(code=1)
        console.print(path.read_text(encoding="utf-8", errors="replace"))
        return

    files = sorted(p for p in artifacts.root.iterdir() if p.is_file())
    if not files:
        warn("No artifacts written yet for this task.")
        return
    for p in files:
        info(str(p.relative_to(project.root)))
