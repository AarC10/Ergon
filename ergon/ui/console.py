from __future__ import annotations

from rich.console import Console

console = Console()


def info(msg: str) -> None:
    console.print(f"[cyan]·[/cyan] {msg}")


def success(msg: str) -> None:
    console.print(f"[green]✓[/green] {msg}")


def warn(msg: str) -> None:
    console.print(f"[yellow]![/yellow] {msg}")


def error(msg: str) -> None:
    console.print(f"[red]✗[/red] {msg}")


def heading(msg: str) -> None:
    console.print()
    console.rule(f"[bold]{msg}")
