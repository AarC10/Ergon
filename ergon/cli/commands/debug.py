from __future__ import annotations

import typer


def run(
    task_id: str = typer.Argument(..., help="Task id"),
    agent: str = typer.Option("openai", "--agent", "-a"),
) -> None:
    """Run the debugger agent for a task."""
    raise typer.Exit(code=0)
