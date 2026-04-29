from __future__ import annotations

import typer
from pydantic import ValidationError
from rich.table import Table

from ergon.core.config import AgentsConfig
from ergon.ui.console import console, error


def run() -> None:
    """List configured agent aliases."""
    try:
        config = AgentsConfig.load()
    except (FileNotFoundError, ValidationError) as e:
        error(str(e))
        raise typer.Exit(code=1) from e

    table = Table(title="Agents", show_header=True)
    table.add_column("Alias", style="cyan", no_wrap=True)
    table.add_column("Backend")
    table.add_column("Command")
    table.add_column("Model")
    table.add_column("Invocation")
    table.add_column("Mode")
    table.add_column("Default role")
    for name in sorted(config.agents):
        definition = config.agents[name]
        table.add_row(
            name,
            definition.backend,
            definition.command,
            definition.model or "-",
            definition.invocation or "-",
            definition.mode,
            definition.default_role or "-",
        )
    console.print(table)
