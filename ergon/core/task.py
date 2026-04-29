from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from textwrap import dedent

from ergon.core.artifact_store import TaskArtifacts
from ergon.core.config import (
    TASK_TYPES,
    ProjectAgents,
    TaskConfig,
    TaskScope,
    ValidationConfig,
)
from ergon.core.project import Project
from ergon.utils.slug import slugify


_TASK_DIR_RE = re.compile(r"^(\d{3,})-(.+)$")


def next_task_id(project: Project) -> str:
    project.tasks_dir.mkdir(parents=True, exist_ok=True)
    highest = 0
    for entry in project.tasks_dir.iterdir():
        if not entry.is_dir():
            continue
        m = _TASK_DIR_RE.match(entry.name)
        if not m:
            continue
        highest = max(highest, int(m.group(1)))
    return f"{highest + 1:03d}"


def find_task_dir(project: Project, task_id: str) -> Path:
    """Resolve task_id (e.g. '1', '001', or full slug-id) to its task folder."""
    project.tasks_dir.mkdir(parents=True, exist_ok=True)
    normalized = task_id.zfill(3) if task_id.isdigit() else task_id
    for entry in project.tasks_dir.iterdir():
        if not entry.is_dir():
            continue
        if entry.name == normalized:
            return entry
        m = _TASK_DIR_RE.match(entry.name)
        if m and (m.group(1) == normalized or entry.name == task_id):
            return entry
    raise FileNotFoundError(f"No task matching '{task_id}' under {project.tasks_dir}")


def load_task(project: Project, task_id: str) -> tuple[TaskConfig, TaskArtifacts]:
    folder = find_task_dir(project, task_id)
    artifacts = TaskArtifacts(root=folder)
    return artifacts.load_task(), artifacts


def create_task(
    project: Project,
    title: str,
    type_: str = "feature",
    goal: str | None = None,
) -> tuple[TaskConfig, TaskArtifacts]:
    """Create a new task folder under .ergon/tasks/."""
    task, artifacts = preview_task(project, title=title, type_=type_, goal=goal)
    artifacts.root.mkdir(parents=True, exist_ok=False)
    artifacts.save_task(task)
    artifacts.write_text("brief.md", _brief_template(task))
    artifacts.write_text("context.md", _context_template(project, task))
    return task, artifacts


def preview_task(
    project: Project,
    title: str,
    type_: str = "feature",
    goal: str | None = None,
    task_id: str | None = None,
) -> tuple[TaskConfig, TaskArtifacts]:
    """Build the task model and artifact paths without writing anything."""
    if type_ not in TASK_TYPES:
        raise ValueError(
            f"Unknown task type '{type_}'. Choose one of: {', '.join(TASK_TYPES)}"
        )

    title = title.strip()
    if not title:
        raise ValueError("Task title cannot be empty.")

    task_id = task_id or next_task_id(project)
    slug = slugify(title)
    if not slug:
        raise ValueError(
            f"Could not derive a slug from title {title!r}. "
            "Use letters / numbers / spaces."
        )
    folder_name = f"{task_id}-{slug}"
    folder = project.tasks_dir / folder_name

    # Project-level excludes are the floor for forbidden_paths; the implementer
    # must never wander into build/ or .git/ even if the task brief is silent.
    forbidden = list(dict.fromkeys([".git/**", *project.config.context.exclude]))

    task = TaskConfig(
        id=task_id,
        title=title,
        slug=slug,
        status="created",
        repo=project.config.name,
        base_branch=project.config.default_branch,
        goal=(goal or title).strip(),
        type=type_,  # type: ignore[arg-type]
        scope=TaskScope(
            allowed_paths=list(project.config.context.include),
            forbidden_paths=forbidden,
        ),
        validation=ValidationConfig(commands=list(project.config.validation.commands)),
        agents=ProjectAgents(**project.config.agents.model_dump()),
        manual_gate=project.config.rules.require_manual_approval,
        safety_level=project.config.rules.safety_level,
    )
    artifacts = TaskArtifacts(root=folder)
    return task, artifacts


def _brief_template(task: TaskConfig) -> str:
    return dedent(
        f"""\
        # Task {task.id}: {task.title}

        Created: {task.created_at.isoformat(timespec='seconds')}
        Type: {task.type}
        Status: {task.status}

        ## Goal

        {task.goal}

        ## Notes

        Add any details, references, or constraints discovered during intake.

        ## Acceptance criteria

        - [ ] (fill in)
        """
    )


def _context_template(project: Project, task: TaskConfig) -> str:
    includes = "\n".join(f"- `{p}`" for p in task.scope.allowed_paths) or "- (none)"
    excludes = "\n".join(f"- `{p}`" for p in task.scope.forbidden_paths) or "- (none)"
    constraints = "\n".join(f"- {c}" for c in task.constraints) or "- (none yet)"
    validation = "\n".join(f"- `{c}`" for c in task.validation.commands) or "- (none)"
    return dedent(
        f"""\
        # Context for task {task.id}

        Repo: {project.config.name} ({project.config.type})
        Base branch: {task.base_branch}
        Safety: {task.safety_level}

        ## Allowed scope

        {includes}

        ## Forbidden scope

        {excludes}

        ## Constraints

        {constraints}

        ## Validation

        {validation}
        """
    )


def update_status(
    artifacts: TaskArtifacts,
    status: str,
) -> TaskConfig:
    task = artifacts.load_task()
    task.status = status  # type: ignore[assignment]
    task.updated_at = datetime.now()
    artifacts.save_task(task)
    return task
