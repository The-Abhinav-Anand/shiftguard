from __future__ import annotations

from typing import Annotated

import typer
import json
import math
from pathlib import Path

from shiftguard.migrations import upgrade_database
from shiftguard.settings import Settings
from shiftguard.datasets.bank import BankDataset
from shiftguard.experiments.config import OutageConfig, StressConfig, load_run_config
from shiftguard.experiments.runner import prepare_baseline_handoff, run_baseline
from shiftguard.experiments.outage_runner import prepare_outage_handoff, run_outage_recovery
from shiftguard.experiments.stress_runner import run_stress_engine


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
    """Run the Gate1 baseline, Gate2 development outage-recovery, or Gate3 stress-engine configuration."""
    run_config = load_run_config(config)
    manifest = json.loads(run_config.dataset_manifest.read_text(encoding="utf-8"))
    dataset = BankDataset.from_clean_csv(run_config.dataset_csv, manifest)
    database_url = context.obj["db_url"] or Settings().db_url
    if isinstance(run_config, StressConfig):
        result = run_stress_engine(dataset, run_config, database_url)
        typer.echo(json.dumps({
            "experiment_id": result.experiment_id,
            "execution_id": result.execution_id,
            "condition_count": len(result.conditions),
            "payload_keys": list(result.payloads.keys()),
            "content_hashes": result.content_hashes,
        }, sort_keys=True))
        return
    if isinstance(run_config, OutageConfig):
        result = run_outage_recovery(prepare_outage_handoff(dataset, run_config), run_config, database_url)
        typer.echo(json.dumps({"experiment_id": result.experiment_id, "execution_id": result.execution_id, "conditions": result.conditions, "comparisons": result.comparisons, "content_hashes": result.content_hashes}, sort_keys=True))
        return
    result = run_baseline(prepare_baseline_handoff(dataset, run_config), run_config, database_url)
    typer.echo(json.dumps({"experiment_id": result.experiment_id, "execution_id": result.execution_id, "metrics": result.metrics, "content_hashes": result.content_hashes}, sort_keys=True))


@app.command()
def worker(
    context: typer.Context,
    poll_interval: float = typer.Option(0.5, "--poll-interval", help="Seconds between queue polls"),
    recovery_interval: float = typer.Option(5.0, "--recovery-interval", help="Seconds between recovery runs"),
    run_once_flag: bool = typer.Option(False, "--once", help="Run once and exit"),
) -> None:
    """Run dedicated background job execution worker and lease recovery loop."""
    if not math.isfinite(poll_interval) or poll_interval <= 0.0:
        typer.echo("Error: --poll-interval must be a positive finite float", err=True)
        raise typer.BadParameter("--poll-interval must be a positive finite float")
    if not math.isfinite(recovery_interval) or recovery_interval <= 0.0:
        typer.echo("Error: --recovery-interval must be a positive finite float", err=True)
        raise typer.BadParameter("--recovery-interval must be a positive finite float")

    import signal
    import threading
    from shiftguard.jobs.queue import JobQueue
    from shiftguard.jobs.worker import ExperimentWorker
    from shiftguard.jobs.recovery import run_recovery_loop
    from shiftguard.storage.db import create_engine_for_settings

    values = {"SHIFTGUARD_DB_URL": context.obj["db_url"]} if context.obj["db_url"] else {}
    settings = Settings(**values)
    upgrade_database(settings)
    engine = create_engine_for_settings(settings)
    queue = JobQueue(engine)
    worker_instance = ExperimentWorker(settings)

    if run_once_flag:
        job = worker_instance.run_once(queue)
        if job:
            typer.echo(f"Executed job {job.id} (status: {job.status.value})")
        else:
            typer.echo("No queued jobs available")
        engine.dispose()
        return

    stop_event = threading.Event()

    def _sig_handler(sig, frame):
        typer.echo("Shutting down worker...")
        stop_event.set()

    signal.signal(signal.SIGINT, _sig_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _sig_handler)

    typer.echo(f"Starting SHIFTGUARD worker {worker_instance.worker_id}...")
    recovery_thread = threading.Thread(
        target=run_recovery_loop,
        args=(engine, settings.artifact_root, stop_event, recovery_interval),
        daemon=True,
        name="cli-recovery",
    )
    recovery_thread.start()

    try:
        worker_instance.run_loop(queue, stop_event=stop_event, poll_interval=poll_interval)
    finally:
        stop_event.set()
        recovery_thread.join(timeout=3.0)
        engine.dispose()
        typer.echo("Worker stopped cleanly.")


def main() -> None:
    app()
