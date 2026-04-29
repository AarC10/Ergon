from __future__ import annotations

import typer

from ergon.agents.base import AgentNotAvailable
from ergon.core.orchestrator import (
    ReviewPreconditionError,
    resolve_reviewer_roles,
    review,
)
from ergon.core.project import Project, ProjectNotInitialized
from ergon.core.task import load_task
from ergon.ui.console import error, info, success, warn


def run(
    task_id: str = typer.Argument(..., help="Task id"),
    agents: list[str] | None = typer.Option(
        None,
        "--agents",
        "-a",
        help="Reviewer agents (defaults to task / project config)",
    ),
) -> None:
    """Have one or more reviewer agents review the diff for a task."""
    try:
        project = Project.discover()
    except ProjectNotInitialized as e:
        error(str(e))
        raise typer.Exit(code=1) from e

    try:
        task, _ = load_task(project, task_id)
    except FileNotFoundError as e:
        error(str(e))
        raise typer.Exit(code=1) from e

    try:
        resolutions = resolve_reviewer_roles(
            explicit=agents,
            task=task,
            project=project,
            fallback=["openai"],
            require_command=True,
        )
    except ValueError as e:
        error(str(e))
        raise typer.Exit(code=2) from e
    chosen = [resolution.selected_agent for resolution in resolutions]

    try:
        task, artifacts, invocations = review(project, task_id, chosen)
    except ReviewPreconditionError as e:
        error(str(e))
        raise typer.Exit(code=1) from e
    except AgentNotAvailable as e:
        error(str(e))
        raise typer.Exit(code=2) from e

    failed = [i for i in invocations if i.exit_code not in (0, None)]
    if failed:
        warn(
            f"{len(failed)} of {len(invocations)} reviewers exited non-zero — "
            "see review-*.md"
        )
    else:
        success(f"{len(invocations)} reviewer(s) wrote feedback")
    info(
        "Resolved reviewers: "
        + ", ".join(
            f"{resolution.selected_agent} ({resolution.source})"
            for resolution in resolutions
        )
    )
    info(f"Summary: {artifacts.review_summary.relative_to(project.root)}")
