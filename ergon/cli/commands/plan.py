from __future__ import annotations

import typer


def run(
    task_id: str = typer.Argument(..., help="Task id, e.g. 001"),
    agent: str = typer.Option("openai", "--agent", "-a", help="Agent name"),
) -> None:
    """Run the planner agent for a task."""
    raise typer.Exit(code=0)
