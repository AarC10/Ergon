from __future__ import annotations

import typer


def run(
    task_id: str = typer.Argument(..., help="Task id"),
    agents: list[str] = typer.Option(
        ["openai"], "--agents", "-a", help="Reviewer agents", show_default=True
    ),
) -> None:
    """Have one or more reviewer agents review the diff for a task."""
    raise typer.Exit(code=0)
