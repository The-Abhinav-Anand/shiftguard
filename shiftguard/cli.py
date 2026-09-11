from __future__ import annotations

from typing import Annotated

import typer

from shiftguard.migrations import upgrade_database
from shiftguard.settings import Settings


app = typer.Typer(no_args_is_help=True)


@app.callback()
def command_group(
    context: typer.Context,
    db_url: Annotated[str | None, typer.Option("--db-url")] = None,
) -> None:
    """SHIFTGUARD command-line interface."""
    context.obj = {"db_url": db_url}


@app.command()
def status(context: typer.Context) -> None:
    """Confirm the Gate0 runtime can initialize its database."""
    values = {"SHIFTGUARD_DB_URL": context.obj["db_url"]} if context.obj["db_url"] else {}
    upgrade_database(Settings(**values))
    typer.echo("Gate 0 bootstrap ready")


def main() -> None:
    app()
