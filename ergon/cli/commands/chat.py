from __future__ import annotations

from pathlib import Path

import typer

from ergon.ui.chat_shell import shell


def run(
    task_id: str | None = typer.Option(None, "--task", "-t", help="Active task id"),
    repo: Path | None = typer.Option(None, "--repo", "-r", help="Repo path"),
) -> None:
    """Start the interactive Ergon shell."""
    shell(initial_repo=repo, initial_task=task_id)
