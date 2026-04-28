from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from pathlib import Path

from rich.panel import Panel
from rich.prompt import Prompt

from ergon.agents.base import AgentNotAvailable
from ergon.core.config import SafetyLevel
from ergon.core.orchestrator import (
    analyze,
    capture_diff,
    debug,
    implement,
    plan,
    review,
    run_validation,
)
from ergon.core.project import Project, ProjectNotInitialized
from ergon.core.task import create_task, find_task_dir, load_task
from ergon.ui.console import console, error, info, success, warn


_HELP = """\
[bold]Ergon shell[/bold]

Slash commands:
  /repo <path>           switch active project (path to a repo with .ergon/)
  /task <id>             set active task
  /start <title>         create a new task and make it active
  /tasks                 list tasks in the active project
  /status [<id>]         show project or task status
  /plan [--agent X]      run planner on the active task
  /implement [--agent X] run implementer in worktree for the active task
  /validate              run validation commands for the active task
  /review [--agents X Y] run reviewers for the active task
  /debug [--agent X]     run debugger for the active task
  /analyze <path>        run analyzer on a file (uses active task if any)
  /diff                  show diff for the active task
  /logs [<file>]         show artifacts for the active task
  /unsafe on | off       toggle unsafe mode (must be explicit)
  /help                  show this help
  /exit                  quit

Anything else is treated as a free-form note appended to the active task's
brief.md (no agent is invoked — Ergon stays explicit).
"""


@dataclass
class Session:
    project: Project | None = None
    active_task_id: str | None = None
    safety: SafetyLevel = "guarded"
    extras: dict[str, str] = field(default_factory=dict)


def shell(initial_repo: Path | None = None, initial_task: str | None = None) -> None:
    session = Session()
    if initial_repo:
        _switch_project(session, initial_repo)
    else:
        try:
            session.project = Project.discover()
        except ProjectNotInitialized:
            session.project = None
    if initial_task and session.project:
        try:
            find_task_dir(session.project, initial_task)
            session.active_task_id = initial_task
        except FileNotFoundError as e:
            warn(str(e))

    console.print(
        Panel(
            "[bold cyan]Ergon[/bold cyan] — type /help for commands, /exit to quit.",
            border_style="cyan",
        )
    )

    while True:
        prompt_str = _format_prompt(session)
        try:
            line = Prompt.ask(prompt_str).strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            return
        if not line:
            continue
        if line in {"/exit", "/quit"}:
            return
        try:
            _handle(session, line)
        except SystemExit:
            # typer.Exit can be raised by underlying command code; suppress in shell.
            pass
        except AgentNotAvailable as e:
            error(str(e))
        except FileNotFoundError as e:
            error(str(e))
        except ProjectNotInitialized as e:
            error(str(e))


def _format_prompt(session: Session) -> str:
    proj = session.project.config.name if session.project else "(no project)"
    task = session.active_task_id or "-"
    safety = session.safety
    return f"[cyan]{proj}[/cyan]/[magenta]{task}[/magenta] ({safety}) >"


def _handle(session: Session, line: str) -> None:
    if not line.startswith("/"):
        _append_note(session, line)
        return

    parts = shlex.split(line)
    cmd = parts[0]
    args = parts[1:]

    handlers = {
        "/help": _cmd_help,
        "/repo": _cmd_repo,
        "/task": _cmd_task,
        "/start": _cmd_start,
        "/tasks": _cmd_tasks,
        "/status": _cmd_status,
        "/plan": _cmd_plan,
        "/implement": _cmd_implement,
        "/validate": _cmd_validate,
        "/review": _cmd_review,
        "/debug": _cmd_debug,
        "/analyze": _cmd_analyze,
        "/diff": _cmd_diff,
        "/logs": _cmd_logs,
        "/unsafe": _cmd_unsafe,
    }
    handler = handlers.get(cmd)
    if handler is None:
        warn(f"Unknown command: {cmd}. Try /help.")
        return
    handler(session, args)


# ---- handlers --------------------------------------------------------------


def _cmd_help(session: Session, args: list[str]) -> None:
    console.print(_HELP)


def _switch_project(session: Session, path: Path) -> None:
    try:
        project = Project.discover(start=path)
    except ProjectNotInitialized as e:
        error(str(e))
        return
    session.project = project
    session.active_task_id = None
    session.safety = project.config.rules.safety_level
    success(f"Active project: {project.config.name} ({project.root})")


def _cmd_repo(session: Session, args: list[str]) -> None:
    if not args:
        error("Usage: /repo <path>")
        return
    _switch_project(session, Path(args[0]).expanduser())


def _need_project(session: Session) -> Project | None:
    if session.project is None:
        error("No active project. Use `/repo <path>` first.")
        return None
    return session.project


def _need_task(session: Session) -> str | None:
    if session.active_task_id is None:
        error("No active task. Use `/task <id>` or `/start <title>`.")
        return None
    return session.active_task_id


def _cmd_task(session: Session, args: list[str]) -> None:
    project = _need_project(session)
    if not project:
        return
    if not args:
        error("Usage: /task <id>")
        return
    try:
        find_task_dir(project, args[0])
    except FileNotFoundError as e:
        error(str(e))
        return
    session.active_task_id = args[0]
    success(f"Active task: {args[0]}")


def _cmd_start(session: Session, args: list[str]) -> None:
    project = _need_project(session)
    if not project:
        return
    if not args:
        error("Usage: /start <title>")
        return
    title = " ".join(args)
    task, artifacts = create_task(project, title=title)
    session.active_task_id = task.id
    success(f"Created task {task.id}: {task.title}")
    info(f"Folder: {artifacts.root.relative_to(project.root)}")


def _cmd_tasks(session: Session, args: list[str]) -> None:
    project = _need_project(session)
    if not project:
        return
    from ergon.cli.commands.tasks import run as tasks_run

    # The CLI command does the right thing already.
    tasks_run()


def _cmd_status(session: Session, args: list[str]) -> None:
    project = _need_project(session)
    if not project:
        return
    from ergon.cli.commands.status import run as status_run

    status_run(args[0] if args else session.active_task_id)


def _agent_arg(args: list[str], default: str) -> str:
    """Tiny `--agent X` parser to avoid pulling Typer into the shell."""
    if "--agent" in args:
        i = args.index("--agent")
        if i + 1 < len(args):
            return args[i + 1]
    if "-a" in args:
        i = args.index("-a")
        if i + 1 < len(args):
            return args[i + 1]
    return default


def _agents_arg(args: list[str], default: list[str]) -> list[str]:
    out: list[str] = []
    take = False
    for a in args:
        if a in {"--agents", "-a"}:
            take = True
            continue
        if take:
            if a.startswith("-"):
                take = False
            else:
                out.append(a)
    return out or default


def _cmd_plan(session: Session, args: list[str]) -> None:
    project = _need_project(session)
    task_id = _need_task(session)
    if not project or not task_id:
        return
    agent = _agent_arg(args, project.config.agents.planner or "openai")
    _, artifacts, inv = plan(project, task_id, agent)
    if inv.exit_code == 0:
        success(f"plan.md written")
    else:
        warn(f"planner exited {inv.exit_code}")


def _cmd_implement(session: Session, args: list[str]) -> None:
    project = _need_project(session)
    task_id = _need_task(session)
    if not project or not task_id:
        return
    agent = _agent_arg(args, project.config.agents.implementer or "claude")
    _, _, inv = implement(project, task_id, agent)
    if inv.exit_code == 0:
        success(f"implementer {agent} done")
    else:
        warn(f"implementer exited {inv.exit_code}")


def _cmd_validate(session: Session, args: list[str]) -> None:
    project = _need_project(session)
    task_id = _need_task(session)
    if not project or not task_id:
        return
    task, artifacts = load_task(project, task_id)
    results = run_validation(project, task, artifacts)
    failed = [r for r in results if not r.ok]
    if not results:
        warn("No validation commands configured.")
    elif failed:
        warn(f"{len(failed)}/{len(results)} validation commands failed")
    else:
        success(f"All {len(results)} validation commands passed")


def _cmd_review(session: Session, args: list[str]) -> None:
    project = _need_project(session)
    task_id = _need_task(session)
    if not project or not task_id:
        return
    agents = _agents_arg(
        args, project.config.agents.reviewers or ["openai"]
    )
    _, _, invs = review(project, task_id, agents)
    failed = [i for i in invs if i.exit_code not in (0, None)]
    if failed:
        warn(f"{len(failed)}/{len(invs)} reviewers exited non-zero")
    else:
        success(f"{len(invs)} reviewer(s) wrote feedback")


def _cmd_debug(session: Session, args: list[str]) -> None:
    project = _need_project(session)
    task_id = _need_task(session)
    if not project or not task_id:
        return
    agent = _agent_arg(args, project.config.agents.debugger or "openai")
    _, _, inv = debug(project, task_id, agent)
    if inv.exit_code == 0:
        success(f"debug-{agent}.md written")
    else:
        warn(f"debugger exited {inv.exit_code}")


def _cmd_analyze(session: Session, args: list[str]) -> None:
    if not args:
        error("Usage: /analyze <path> [--agent X]")
        return
    target = Path(args[0]).expanduser().resolve()
    agent = _agent_arg(args, "gemini")
    _, inv = analyze(
        project=session.project,
        target=target,
        input_kind="auto",
        agent_name=agent,
        task_id=session.active_task_id if session.project else None,
    )
    if inv.exit_code == 0:
        success("analysis written")
    else:
        warn(f"analyzer exited {inv.exit_code}")


def _cmd_diff(session: Session, args: list[str]) -> None:
    project = _need_project(session)
    task_id = _need_task(session)
    if not project or not task_id:
        return
    task, artifacts = load_task(project, task_id)
    capture_diff(project, task, artifacts)
    if not artifacts.diff_patch.exists() or not artifacts.diff_patch.read_text().strip():
        warn("diff.patch is empty.")
        return
    from rich.syntax import Syntax

    body = artifacts.diff_patch.read_text(encoding="utf-8", errors="replace")
    console.print(Syntax(body, "diff", theme="ansi_dark"))


def _cmd_logs(session: Session, args: list[str]) -> None:
    project = _need_project(session)
    task_id = _need_task(session)
    if not project or not task_id:
        return
    _, artifacts = load_task(project, task_id)
    if args:
        path = artifacts.root / args[0]
        if not path.exists():
            error(f"No such artifact: {args[0]}")
            return
        console.print(path.read_text(encoding="utf-8", errors="replace"))
    else:
        for p in sorted(artifacts.root.iterdir()):
            if p.is_file():
                info(p.name)


def _cmd_unsafe(session: Session, args: list[str]) -> None:
    if not args or args[0] not in {"on", "off"}:
        error("Usage: /unsafe on|off")
        return
    if args[0] == "on":
        session.safety = "unsafe"
        warn("unsafe mode active for this session — agents have broader command access.")
    else:
        if session.project:
            session.safety = session.project.config.rules.safety_level
        else:
            session.safety = "guarded"
        success(f"safety restored to {session.safety}")


def _append_note(session: Session, text: str) -> None:
    project = _need_project(session)
    task_id = _need_task(session)
    if not project or not task_id:
        info("(no active task — note discarded)")
        return
    _, artifacts = load_task(project, task_id)
    artifacts.append_text(
        "brief.md",
        f"\n\n> note ({session.safety}): {text}\n",
    )
    info("note appended to brief.md")
