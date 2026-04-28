from __future__ import annotations

import typer

from ergon.agents.base import AgentNotAvailable
from ergon.core.orchestrator import review
from ergon.core.project import Project, ProjectNotInitialized
from ergon.ui.console import error, info, success, warn


def run(
    task_id: str = typer.Argument(..., help="Task id"),
    agents: list[str] = typer.Option(
        ["openai"], "--agents", "-a", help="Reviewer agents", show_default=True
    ),
) -> None:
    """Have one or more reviewer agents review the diff for a task."""
    try:
        project = Project.discover()
    except ProjectNotInitialized as e:
        error(str(e))
        raise typer.Exit(code=1) from e

    try:
        task, artifacts, invocations = review(project, task_id, agents)
    except (AgentNotAvailable, FileNotFoundError) as e:
        error(str(e))
        raise typer.Exit(code=1) from e

    failed = [i for i in invocations if i.exit_code not in (0, None)]
    if failed:
        warn(
            f"{len(failed)} of {len(invocations)} reviewers exited non-zero — "
            "see review-*.md"
        )
    else:
        success(f"{len(invocations)} reviewer(s) wrote feedback")
    info(f"Summary: {artifacts.review_summary.relative_to(project.root)}")
