from __future__ import annotations

import typer

from ergon.core.orchestrator import capture_diff
from ergon.core.project import Project, ProjectNotInitialized
from ergon.core.task import load_task
from ergon.ui.console import console, error, warn


def run(
    task_id: str = typer.Argument(..., help="Task id"),
    refresh: bool = typer.Option(
        False, "--refresh", help="Re-run diff capture against the worktree first"
    ),
) -> None:
    """Show the captured diff for a task."""
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

    if refresh:
        capture_diff(project, task, artifacts)

    if not artifacts.diff_patch.exists():
        warn("No diff captured yet. Run `ergon implement` or `ergon diff <id> --refresh`.")
        raise typer.Exit(code=1)

    body = artifacts.diff_patch.read_text(encoding="utf-8", errors="replace")
    if not body.strip():
        warn("diff.patch is empty.")
        return
    # Pipe the patch through Rich's syntax highlighter for readability.
    from rich.syntax import Syntax

    console.print(Syntax(body, "diff", theme="ansi_dark", word_wrap=False))
