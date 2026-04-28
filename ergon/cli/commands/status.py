from __future__ import annotations

import typer


def run(task_id: str | None = typer.Argument(None, help="Optional task id")) -> None:
    """Show project / task status."""
    raise typer.Exit(code=0)
