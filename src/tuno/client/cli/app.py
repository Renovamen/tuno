"""Typer CLI application for the tuno terminal client."""

import typer

from tuno import __version__
from tuno.client.cli.uninstall import cli_uninstall
from tuno.client.cli.update import cli_self_update
from tuno.client.tui.app import run_client

app = typer.Typer(help="Tuno - a terminal-first UNO game.", invoke_without_command=True)


@app.callback()
def main(
    ctx: typer.Context,
    server: str | None = typer.Option(None, "-s", "--server", help="ws:// or wss:// server URL to connect on startup."),
) -> None:
    if ctx.invoked_subcommand is None:
        run_client(server_url=server or "")


@app.command()
def update() -> None:
    """Update the installed tuno client."""
    cli_self_update(__version__)


@app.command()
def uninstall() -> None:
    """Uninstall the tuno client."""
    cli_uninstall()
