from __future__ import annotations

import typer


def run(title: str = typer.Argument(..., help="Short title for the new task")) -> None:
    """Create a new task from a short natural language title."""
    raise typer.Exit(code=0)
