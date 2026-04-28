from __future__ import annotations

from pathlib import Path

import typer


def run(
    target: Path = typer.Argument(..., help="File or directory to analyze"),
    type_: str = typer.Option("log", "--type", "-t", help="Input type"),
    agent: str = typer.Option("gemini", "--agent", "-a"),
    task_id: str | None = typer.Option(None, "--task", help="Attach to existing task"),
) -> None:
    """Run the analyzer agent against an input file or directory."""
    raise typer.Exit(code=0)
