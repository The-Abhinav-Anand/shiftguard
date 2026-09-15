from __future__ import annotations

from typing import Annotated

import typer
import json
from pathlib import Path

from shiftguard.migrations import upgrade_database
from shiftguard.settings import Settings
from shiftguard.datasets.bank import BankDataset
from shiftguard.experiments.config import OutageConfig, load_run_config
from shiftguard.experiments.runner import prepare_baseline_handoff, run_baseline
from shiftguard.experiments.outage_runner import prepare_outage_handoff, run_outage_recovery


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


@app.command()
def run(
    context: typer.Context,
    config: Path = typer.Option(..., "--config", exists=True, readable=True),
) -> None:
    """Run the Gate1 baseline or Gate2 development outage-recovery configuration."""
    run_config = load_run_config(config)
    manifest = json.loads(run_config.dataset_manifest.read_text(encoding="utf-8"))
    dataset = BankDataset.from_clean_csv(run_config.dataset_csv, manifest)
    database_url = context.obj["db_url"] or Settings().db_url
    if isinstance(run_config, OutageConfig):
        result = run_outage_recovery(prepare_outage_handoff(dataset, run_config), run_config, database_url)
        typer.echo(json.dumps({"experiment_id": result.experiment_id, "execution_id": result.execution_id, "conditions": result.conditions, "comparisons": result.comparisons, "content_hashes": result.content_hashes}, sort_keys=True))
        return
    result = run_baseline(prepare_baseline_handoff(dataset, run_config), run_config, database_url)
    typer.echo(json.dumps({"experiment_id": result.experiment_id, "execution_id": result.execution_id, "metrics": result.metrics, "content_hashes": result.content_hashes}, sort_keys=True))


def main() -> None:
    app()
