from __future__ import annotations

import typer


def run(task_id: str = typer.Argument(..., help="Task id")) -> None:
    """Show the captured diff for a task."""
    raise typer.Exit(code=0)
