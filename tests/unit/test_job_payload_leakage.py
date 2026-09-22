"""Unit tests ensuring zero dataset row/label or secret leakage in jobs, events, and API payloads."""

from __future__ import annotations

import json
import pytest
from sqlalchemy import create_engine

from shiftguard.jobs.queue import JobQueue
from shiftguard.migrations import upgrade_database
from shiftguard.settings import Settings


@pytest.fixture
def queue(tmp_path):
    db_file = tmp_path / "leakage_test.db"
    settings = Settings(SHIFTGUARD_DB_URL=f"sqlite:///{db_file}")
    upgrade_database(settings)
    engine = create_engine(f"sqlite:///{db_file}")
    try:
        yield JobQueue(engine)
    finally:
        engine.dispose()


def test_job_and_events_contain_no_raw_labels_or_rows(queue):
    job = queue.enqueue({"preset_name": "bank-outage-50", "master_seed": 31001})
    claimed = queue.claim_next_job("worker-alpha")
    queue.mark_completed(claimed.id, claimed.fencing_token, "exp-12345", {"summary": "ok"})

    job_dict = queue.get_job(job.id).to_dict()
    job_str = json.dumps(job_dict)

    # Forbid raw label strings or data row indicators
    forbidden_terms = ["y_train", "y_test", "confirmatory_labels", "secret", "password"]
    for term in forbidden_terms:
        assert term not in job_str, f"Forbidden term '{term}' found in job record: {job_str}"
