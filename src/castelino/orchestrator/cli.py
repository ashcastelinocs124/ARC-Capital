"""ARC Capital CLI — `ckm serve` starts the dashboard backend."""

from __future__ import annotations

import typer
from rich import print as rich_print

app = typer.Typer(help="ARC Capital — multi-agent macro fund.", no_args_is_help=True)


@app.callback()
def main() -> None:
    """Keeps `serve` a named subcommand (typer collapses single-command apps)."""


@app.command()
def serve(
    port: int = typer.Option(7779, help="Port for the OpenBB backend."),
    reload: bool = typer.Option(False, help="Enable auto-reload for development."),
):
    """Start the OpenBB Workspace dashboard backend."""
    import uvicorn

    rich_print(f"[green]Starting ARC Capital dashboard on port {port}[/green]")
    rich_print(
        "[blue]Connect in OpenBB Workspace: Settings → Data Connectors → Add http://localhost:"
        f"{port}[/blue]"
    )
    uvicorn.run("castelino.dashboard.main:app", host="0.0.0.0", port=port, reload=reload)
