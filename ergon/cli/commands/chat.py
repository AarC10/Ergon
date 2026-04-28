from __future__ import annotations

import typer


def run(
    task_id: str | None = typer.Option(None, "--task", "-t", help="Active task id"),
    repo: str | None = typer.Option(None, "--repo", "-r", help="Repo path or name"),
) -> None:
    """Start the interactive Ergon shell."""
    raise typer.Exit(code=0)
