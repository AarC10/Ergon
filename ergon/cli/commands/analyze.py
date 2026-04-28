from __future__ import annotations

from pathlib import Path

import typer

from ergon.agents.base import AgentNotAvailable
from ergon.core.orchestrator import analyze
from ergon.core.project import Project, ProjectNotInitialized
from ergon.ui.console import error, info, success, warn


def run(
    target: Path = typer.Argument(..., help="File or directory to analyze"),
    type_: str = typer.Option("log", "--type", "-t", help="Input type"),
    agent: str = typer.Option("gemini", "--agent", "-a"),
    task_id: str | None = typer.Option(None, "--task", help="Attach to existing task"),
) -> None:
    """Run the analyzer agent against an input file or directory."""
    project: Project | None
    try:
        project = Project.discover()
    except ProjectNotInitialized:
        project = None
        if task_id:
            error("--task requires running inside an Ergon project")
            raise typer.Exit(code=1)

    try:
        artifacts, invocation = analyze(
            project=project,
            target=target.resolve(),
            input_kind=type_,
            agent_name=agent,
            task_id=task_id,
        )
    except (AgentNotAvailable, FileNotFoundError) as e:
        error(str(e))
        raise typer.Exit(code=1) from e

    if invocation.exit_code == 0:
        success(f"Analysis from {agent} complete")
    else:
        warn(f"Analyzer exited with code {invocation.exit_code}")
    if artifacts:
        info(f"Wrote analyze-{agent}.md inside {artifacts.root}")
    else:
        info(f"Wrote {target.stem}.analysis-{agent}.md alongside the input")
