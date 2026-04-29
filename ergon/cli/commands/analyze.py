from __future__ import annotations

from pathlib import Path

import typer

from ergon.agents.base import AgentNotAvailable
from ergon.core.orchestrator import analyze, resolve_agent_choice
from ergon.core.project import Project, ProjectNotInitialized
from ergon.core.task import load_task
from ergon.ui.console import error, info, success, warn


def run(
    target: Path = typer.Argument(..., help="File or directory to analyze"),
    type_: str = typer.Option("log", "--type", "-t", help="Input type"),
    agent: str | None = typer.Option(
        None, "--agent", "-a", help="Analyzer agent (overrides project / task default)"
    ),
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

    task = None
    if project and task_id:
        try:
            task, _ = load_task(project, task_id)
        except FileNotFoundError as e:
            error(str(e))
            raise typer.Exit(code=1) from e

    chosen: str
    if project:
        chosen = resolve_agent_choice(
            explicit=agent,
            task=task,
            project=project,
            role="analyzer",
            fallback="gemini",
        )
    else:
        chosen = agent or "gemini"

    try:
        artifacts, invocation = analyze(
            project=project,
            target=target.resolve(),
            input_kind=type_,
            agent_name=chosen,
            task_id=task_id,
        )
    except AgentNotAvailable as e:
        error(str(e))
        raise typer.Exit(code=1) from e
    except FileNotFoundError as e:
        error(str(e))
        raise typer.Exit(code=1) from e

    if invocation.exit_code == 0:
        success(f"Analysis from {chosen} complete")
    else:
        warn(f"Analyzer exited with code {invocation.exit_code}")
    if artifacts:
        info(f"Wrote analyze-{chosen}.md inside {artifacts.root}")
    else:
        info(f"Wrote {target.stem}.analysis-{chosen}.md alongside the input")
