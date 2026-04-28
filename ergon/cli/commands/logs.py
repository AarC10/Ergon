from __future__ import annotations

import typer


def run(
    task_id: str = typer.Argument(..., help="Task id"),
    artifact: str | None = typer.Option(None, "--file", "-f", help="Specific log file"),
) -> None:
    """Show task logs."""
    raise typer.Exit(code=0)
