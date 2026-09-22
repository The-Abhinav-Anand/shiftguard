"""ML execution worker with independent heartbeat thread, fencing, and cooperative cancellation."""

from __future__ import annotations

from dataclasses import replace
import logging
import os
from pathlib import Path
import threading
import time
from typing import Any
from uuid import uuid4

import json
from shiftguard.datasets.bank import BankDataset
from shiftguard.experiments.config import BaselineConfig, OutageConfig, StressConfig
from shiftguard.experiments.outage_runner import prepare_outage_handoff, run_outage_recovery
from shiftguard.experiments.runner import prepare_baseline_handoff, run_baseline
from shiftguard.experiments.stress_runner import run_stress_engine
from shiftguard.jobs.models import JobRecord
from shiftguard.jobs.queue import JobQueue
from shiftguard.settings import Settings
from shiftguard.storage.db import create_engine_for_settings

logger = logging.getLogger(__name__)


from shiftguard.jobs.models import WorkerCancelledException, WorkerFencedOutException


class ExperimentWorker:
    def __init__(
        self,
        settings: Settings,
        worker_id: str | None = None,
        heartbeat_interval: int = 30,
        lease_seconds: int = 90,
    ):
        self.settings = settings
        self.worker_id = worker_id or f"worker-{os.getpid()}-{uuid4().hex[:8]}"
        self.heartbeat_interval = heartbeat_interval
        self.lease_seconds = lease_seconds
        self._shutdown_event = threading.Event()

    def run_loop(
        self,
        queue: JobQueue,
        stop_event: threading.Event | None = None,
        poll_interval: float | None = None,
    ) -> None:
        """Continuously poll and execute jobs until stop_event is set."""
        stop = stop_event or self._shutdown_event
        interval = poll_interval if poll_interval is not None else 0.5
        while not stop.is_set():
            try:
                job = self.run_once(queue)
                if not job:
                    stop.wait(interval)
            except Exception as exc:
                logger.exception("Unexpected error in worker loop: %s", exc)
                stop.wait(interval)

    def run_once(self, queue: JobQueue) -> JobRecord | None:
        """Claim and execute a single job if available."""
        job = queue.claim_next_job(
            worker_id=self.worker_id,
            lease_seconds=self.lease_seconds,
        )
        if not job:
            return None

        self.execute_job(job, queue)
        return queue.get_job(job.id)

    def execute_job(self, job: JobRecord, queue: JobQueue) -> None:
        """Execute a claimed job with active heartbeat and cooperative cancellation."""
        fencing_token = job.fencing_token
        if not fencing_token:
            raise ValueError("Cannot execute job without fencing token")

        stop_heartbeat = threading.Event()
        fenced_out = threading.Event()

        # Dedicated heartbeat thread on independent database connection
        def _heartbeat_worker():
            hb_engine = create_engine_for_settings(self.settings)
            try:
                while not stop_heartbeat.is_set():
                    time.sleep(self.heartbeat_interval)
                    if stop_heartbeat.is_set():
                        break
                    hb_queue = JobQueue(hb_engine)
                    success = hb_queue.heartbeat(
                        job_id=job.id,
                        fencing_token=fencing_token,
                        lease_seconds=self.lease_seconds,
                    )
                    if not success:
                        fenced_out.set()
                        break
            finally:
                hb_engine.dispose()

        hb_thread = threading.Thread(target=_heartbeat_worker, daemon=True)
        hb_thread.start()

        def check_cancellation_and_fence():
            if fenced_out.is_set():
                raise WorkerFencedOutException(f"Worker {self.worker_id} was fenced out for job {job.id}")
            if queue.is_cancellation_requested(job.id, fencing_token):
                raise WorkerCancelledException(f"Job {job.id} cancellation requested")

        try:
            params = job.request_params
            preset_name = params.get("preset_name") or "bank-outage-50"
            overrides = params.get("overrides") or {}
            if not isinstance(overrides, dict):
                overrides = {}

            # Cooperative check before heavy work
            check_cancellation_and_fence()

            database_url = self.settings.db_url
            override_seed = overrides.get("seed")
            seed = override_seed if override_seed is not None else 31001

            publish_kwargs = {
                "is_cancelled": check_cancellation_and_fence,
                "fencing_token": fencing_token,
                "queue": queue,
                "job_id": job.id,
                "attempt": job.attempt,
                "settings": self.settings,
            }

            if preset_name == "bank-stress" or params.get("experiment_type") == "stress":
                config = StressConfig(master_seed=seed)
                config = replace(config, artifact_root=self.settings.artifact_root)
                manifest = json.loads(config.dataset_manifest.read_text(encoding="utf-8"))
                dataset = BankDataset.from_clean_csv(config.dataset_csv, manifest)
                res = run_stress_engine(dataset, config, database_url, **publish_kwargs)
            elif preset_name == "bank-outage-50" or params.get("experiment_type") == "outage":
                config = OutageConfig(master_seed=seed)
                config = replace(config, artifact_root=self.settings.artifact_root)
                manifest = json.loads(config.dataset_manifest.read_text(encoding="utf-8"))
                dataset = BankDataset.from_clean_csv(config.dataset_csv, manifest)
                res = run_outage_recovery(prepare_outage_handoff(dataset, config), config, database_url, **publish_kwargs)
            else:
                config = BaselineConfig(master_seed=seed)
                config = replace(config, artifact_root=self.settings.artifact_root)
                manifest = json.loads(config.dataset_manifest.read_text(encoding="utf-8"))
                dataset = BankDataset.from_clean_csv(config.dataset_csv, manifest)
                res = run_baseline(prepare_baseline_handoff(dataset, config), config, database_url, **publish_kwargs)

            # Cooperative check before completion commit
            check_cancellation_and_fence()

            experiment_id = getattr(res, "experiment_id", None) or (res.get("experiment_id") if isinstance(res, dict) else str(res))
            queue.mark_completed(
                job_id=job.id,
                fencing_token=fencing_token,
                experiment_id=experiment_id,
                result_data={"experiment_id": experiment_id, "preset_name": preset_name},
            )

        except WorkerCancelledException:
            queue.mark_cancelled_by_worker(job.id, fencing_token)
        except WorkerFencedOutException as exc:
            logger.warning("Worker fenced out: %s", exc)
            # Stale worker does nothing to database
        except Exception as exc:
            if queue.is_cancellation_requested(job.id, fencing_token):
                queue.mark_cancelled_by_worker(job.id, fencing_token)
            else:
                err = {
                    "code": "EXECUTION_ERROR",
                    "message": str(exc),
                    "error_type": exc.__class__.__name__,
                }
                queue.mark_failed(job.id, fencing_token, err, retryable=False)
        finally:
            stop_heartbeat.set()
            hb_thread.join(timeout=2.0)
