from __future__ import annotations

import typer

from ergon.core.orchestrator import run_validation
from ergon.core.project import Project, ProjectNotInitialized
from ergon.core.task import load_task, update_status
from ergon.ui.console import error, info, success, warn


def run(task_id: str = typer.Argument(..., help="Task id")) -> None:
    """Run validation commands inside the task's worktree."""
    try:
        project = Project.discover()
    except ProjectNotInitialized as e:
        error(str(e))
        raise typer.Exit(code=1) from e

    try:
        task, artifacts = load_task(project, task_id)
    except FileNotFoundError as e:
        error(str(e))
        raise typer.Exit(code=1) from e

    update_status(artifacts, "validating")
    if not task.worktree_path:
        error(f"Task {task.id} has no worktree. Run `ergon implement` first.")
        raise typer.Exit(code=1)

    results = run_validation(project, task, artifacts)
    info(f"Wrote {artifacts.validation_log.relative_to(project.root)}")

    failed = [r for r in results if not r.ok]
    if not results:
        warn("No validation commands configured for this task.")
    elif failed:
        warn(f"{len(failed)} of {len(results)} validation commands failed")
        raise typer.Exit(code=1)
    else:
        success(f"All {len(results)} validation commands passed")
