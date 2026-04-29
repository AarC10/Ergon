from __future__ import annotations

import typer

from ergon.cli.commands import (
    agents as agents_cmd,
    analyze as analyze_cmd,
    chat as chat_cmd,
    debug as debug_cmd,
    diff as diff_cmd,
    implement as implement_cmd,
    init as init_cmd,
    logs as logs_cmd,
    plan as plan_cmd,
    roles as roles_cmd,
    run as run_cmd,
    review as review_cmd,
    start as start_cmd,
    status as status_cmd,
    tasks as tasks_cmd,
    validate as validate_cmd,
)


app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Ergon — local-first multi-agent software engineering helper.",
    pretty_exceptions_show_locals=False,
)


app.command("init")(init_cmd.run)
app.command("start")(start_cmd.run)
app.command("run")(run_cmd.run)
app.command("agents")(agents_cmd.run)
app.command("roles")(roles_cmd.run)
app.command("plan")(plan_cmd.run)
app.command("implement")(implement_cmd.run)
app.command("validate")(validate_cmd.run)
app.command("review")(review_cmd.run)
app.command("analyze")(analyze_cmd.run)
app.command("debug")(debug_cmd.run)
app.command("status")(status_cmd.run)
app.command("tasks")(tasks_cmd.run)
app.command("logs")(logs_cmd.run)
app.command("diff")(diff_cmd.run)
app.command("chat")(chat_cmd.run)
