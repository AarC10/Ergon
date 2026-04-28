from __future__ import annotations

from pathlib import Path

import typer

from ergon.ui.console import error, info, success, warn


def run(
    repo_path: Path = typer.Option(
        Path("."),
        "--path",
        "-p",
        help="Path to the git repo to initialize. Defaults to cwd.",
    ),
    name: str | None = typer.Option(None, "--name", help="Project name"),
    project_type: str = typer.Option(
        "generic",
        "--type",
        "-t",
        help="Project type: embedded-zephyr | roblox-rojo | ros2 | python | generic",
    ),
    force: bool = typer.Option(False, "--force", help="Re-init even if .ergon exists"),
) -> None:
    """Initialize an .ergon/ directory in a git repository."""
    from ergon.core.bootstrap import init_project

    repo_path = repo_path.resolve()
    if not (repo_path / ".git").exists():
        error(f"{repo_path} is not a git repository (no .git/).")
        raise typer.Exit(code=1)

    ergon_dir = repo_path / ".ergon"
    if ergon_dir.exists() and not force:
        warn(f"{ergon_dir} already exists. Use --force to overwrite project.yaml.")
        raise typer.Exit(code=1)

    project_name = name or repo_path.name
    init_project(
        repo_path=repo_path,
        name=project_name,
        project_type=project_type,
        force=force,
    )
    success(f"Initialized Ergon project '{project_name}' at {ergon_dir}")
    info("Edit .ergon/project.yaml to set validation commands and agents.")
