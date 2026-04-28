from __future__ import annotations

import typer


def run(
    task_id: str = typer.Argument(..., help="Task id"),
    agent: str = typer.Option("claude", "--agent", "-a", help="Agent name"),
    extra: str | None = typer.Option(None, "--extra", help="Extra prompt text"),
) -> None:
    """Invoke the implementer agent for a task in its worktree."""
    raise typer.Exit(code=0)
