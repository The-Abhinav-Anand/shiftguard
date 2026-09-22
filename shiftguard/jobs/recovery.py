"""Lease recovery and staging cleanup for Gate 4 durable runtime."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import time

import threading
from typing import Any

from sqlalchemy import text

from shiftguard.jobs.models import JobEventType, JobStatus, utc_now_str
from shiftguard.jobs.queue import JobQueue


def recover_expired_leases(queue_or_engine: Any) -> int:
    """Find and recover expired worker leases.
    
    If attempt < max_attempts and not cancelled, requeues the job.
    Otherwise marks terminal failed or cancelled.
    """
    engine = getattr(queue_or_engine, "engine", queue_or_engine)
    now_str = utc_now_str()
    recovered_count = 0

    with engine.begin() as conn:
        expired_jobs = conn.execute(
            text("""
                SELECT id, attempt, max_attempts, cancel_requested, fencing_token
                FROM jobs
                WHERE status = 'running' AND lease_expires_at < :now
            """),
            {"now": now_str},
        ).mappings().fetchall()

        for row in expired_jobs:
            job_id = row["id"]
            attempt = int(row["attempt"])
            max_attempts = int(row["max_attempts"])
            cancel_requested = bool(row["cancel_requested"])
            token = row["fencing_token"]

            if cancel_requested:
                res = conn.execute(
                    text("""
                        UPDATE jobs SET
                            status = 'cancelled',
                            completed_at = :now
                        WHERE id = :job_id 
                          AND status = 'running' 
                          AND fencing_token = :token 
                          AND lease_expires_at < :now
                    """),
                    {"job_id": job_id, "token": token, "now": now_str},
                )
                if res.rowcount > 0:
                    conn.execute(
                        text("""
                            INSERT INTO job_events (job_id, event_type, fencing_token, details_json, created_at)
                            VALUES (:job_id, :event_type, :fencing_token, :details_json, :created_at)
                        """),
                        {
                            "job_id": job_id,
                            "event_type": JobEventType.CANCELLED.value,
                            "fencing_token": token,
                            "details_json": json.dumps({"reason": "lease_expired_while_cancellation_requested"}),
                            "created_at": now_str,
                        },
                    )
                    recovered_count += 1
            elif attempt < max_attempts:
                res = conn.execute(
                    text("""
                        UPDATE jobs SET
                            status = 'queued',
                            worker_id = NULL,
                            fencing_token = NULL,
                            lease_expires_at = NULL,
                            heartbeat_at = NULL
                        WHERE id = :job_id 
                          AND status = 'running' 
                          AND fencing_token = :token 
                          AND lease_expires_at < :now
                    """),
                    {"job_id": job_id, "token": token, "now": now_str},
                )
                if res.rowcount > 0:
                    conn.execute(
                        text("""
                            INSERT INTO job_events (job_id, event_type, fencing_token, details_json, created_at)
                            VALUES (:job_id, :event_type, :fencing_token, :details_json, :created_at)
                        """),
                        {
                            "job_id": job_id,
                            "event_type": JobEventType.REQUEUED.value,
                            "fencing_token": token,
                            "details_json": json.dumps({"reason": "lease_expired", "attempt": attempt}),
                            "created_at": now_str,
                        },
                    )
                    recovered_count += 1
            else:
                err = {
                    "code": "LEASE_EXPIRED_MAX_ATTEMPTS",
                    "message": f"Worker lease expired and retry limit reached ({attempt}/{max_attempts})",
                }
                res = conn.execute(
                    text("""
                        UPDATE jobs SET
                            status = 'failed',
                            error_json = :error_json,
                            completed_at = :now
                        WHERE id = :job_id 
                          AND status = 'running' 
                          AND fencing_token = :token 
                          AND lease_expires_at < :now
                    """),
                    {
                        "job_id": job_id,
                        "token": token,
                        "error_json": json.dumps(err),
                        "now": now_str,
                    },
                )
                if res.rowcount > 0:
                    conn.execute(
                        text("""
                            INSERT INTO job_events (job_id, event_type, fencing_token, details_json, created_at)
                            VALUES (:job_id, :event_type, :fencing_token, :details_json, :created_at)
                        """),
                        {
                            "job_id": job_id,
                            "event_type": JobEventType.FAILED.value,
                            "fencing_token": token,
                            "details_json": json.dumps(err),
                            "created_at": now_str,
                        },
                    )
                    recovered_count += 1

    return recovered_count


def recover_prepared_publications(
    queue_or_engine: Any,
    artifact_root: Path,
) -> int:
    """Recover or quarantine publications stranded in PREPARED state after worker crash.

    Explicit recovery transitions:
    - Jobless CLI publications with unexpired leases are strictly protected (R4-01).
    - Never resurrect terminal jobs (cancelled or failed) -> marks preparation QUARANTINED.
    - Active running jobs with valid unexpired leases are strictly protected and left untouched.
    - Stale attempts or mismatched fencing tokens are quarantined.
    - Before creating any result rows, identity is validated: stable_hash(payload) must equal
      full_digest, and full_digest[:24] must equal experiment_id (R4-03).
    - Each per-publication attempt is wrapped in a SAVEPOINT; on rejected job transition the
      savepoint is rolled back so no experiment/execution rows are committed (R4-02).
    - Eligible crashed jobs reconstruct canonical content hashes and experiment/execution rows
      using the unified repository validation, atomically complete the job with result linkage
      and COMPLETED event, and mark publication PUBLISHED.
    - Preparations with missing or corrupt metadata/files are safely QUARANTINED.
    """
    import hashlib
    from shiftguard.experiments.ids import stable_hash as recompute_hash
    from shiftguard.storage.repositories import ExperimentRepository, canonical_content_hashes

    engine = getattr(queue_or_engine, "engine", queue_or_engine)
    repo = ExperimentRepository(engine)
    now_str = utc_now_str()
    recovered = 0

    with engine.begin() as conn:
        prepared = conn.execute(
            text("""
                SELECT generation_id, experiment_id, full_digest, execution_id, manifest_json, created_at,
                       job_id, lease_expires_at, prepared_payload_json, prepared_audit_json, attempt, fencing_token
                FROM experiment_publications
                WHERE status = 'PREPARED'
            """)
        ).mappings().fetchall()

        for row in prepared:
            gen_id = row["generation_id"]
            exp_id = row["experiment_id"]
            full_digest = row["full_digest"]
            exec_id = row["execution_id"]
            job_id = row["job_id"]
            pub_attempt = row.get("attempt")
            pub_fencing_token = row.get("fencing_token")
            staging_dir = artifact_root / ".staging" / gen_id

            # ── C03: Isolate manifest JSON decoding per generation ──
            try:
                manifest = json.loads(row["manifest_json"])
                if not isinstance(manifest, dict):
                    raise ValueError("manifest_json must be a dict")
            except Exception:
                conn.execute(
                    text("UPDATE experiment_publications SET status = 'QUARANTINED', updated_at = :now WHERE generation_id = :gen_id"),
                    {"gen_id": gen_id, "now": now_str},
                )
                shutil.rmtree(staging_dir, ignore_errors=True)
                recovered += 1
                continue

            # ── R4-01: Protect jobless CLI owners with unexpired leases ──
            if not job_id:
                pub_lease = row["lease_expires_at"]
                if pub_lease and pub_lease > now_str:
                    # Live CLI owner: do NOT quarantine or touch staging
                    continue

            # If associated with a job, check job state and lease
            job_row = None
            if job_id:
                job_row = conn.execute(
                    text("SELECT status, cancel_requested, fencing_token, attempt, lease_expires_at FROM jobs WHERE id = :job_id"),
                    {"job_id": job_id},
                ).mappings().fetchone()

                if job_row is None:
                    # Job does not exist: cannot complete a non-existent job
                    conn.execute(
                        text("UPDATE experiment_publications SET status = 'QUARANTINED', updated_at = :now WHERE generation_id = :gen_id"),
                        {"gen_id": gen_id, "now": now_str},
                    )
                    shutil.rmtree(staging_dir, ignore_errors=True)
                    recovered += 1
                    continue

                # Never overwrite terminal state or cancelled jobs
                if job_row["status"] in ("cancelled", "failed") or job_row["cancel_requested"]:
                    conn.execute(
                        text("UPDATE experiment_publications SET status = 'QUARANTINED', updated_at = :now WHERE generation_id = :gen_id"),
                        {"gen_id": gen_id, "now": now_str},
                    )
                    shutil.rmtree(staging_dir, ignore_errors=True)
                    recovered += 1
                    continue

                # ── C02: Stale attempt / token check ──
                # If publication has attempt or fencing_token, it MUST match the job's current attempt and token.
                # If publication has no attempt (legacy), but job is at attempt > 1, the generation is stale.
                is_stale_attempt = False
                if pub_attempt is not None and pub_attempt != job_row["attempt"]:
                    is_stale_attempt = True
                elif pub_fencing_token is not None and pub_fencing_token != job_row["fencing_token"]:
                    is_stale_attempt = True
                elif pub_attempt is None and pub_fencing_token is None and (job_row["attempt"] or 1) > 1:
                    is_stale_attempt = True

                if is_stale_attempt:
                    conn.execute(
                        text("UPDATE experiment_publications SET status = 'QUARANTINED', updated_at = :now WHERE generation_id = :gen_id"),
                        {"gen_id": gen_id, "now": now_str},
                    )
                    shutil.rmtree(staging_dir, ignore_errors=True)
                    recovered += 1
                    continue

                # Active running job holding valid lease: strictly leave alone!
                if job_row["status"] in ("running", "claimed"):
                    lease_exp = job_row["lease_expires_at"] or row["lease_expires_at"]
                    if lease_exp and lease_exp > now_str:
                        continue

            # Check target directory on disk
            target_dir = artifact_root / exp_id
            matches = False
            if target_dir.is_dir() and manifest:
                matches = True
                for rel_path, expected_hash in manifest.items():
                    target_file = target_dir / rel_path
                    if not target_file.is_file():
                        matches = False
                        break
                    try:
                        h = hashlib.sha256(target_file.read_bytes()).hexdigest()
                        if h != expected_hash:
                            matches = False
                            break
                    except OSError:
                        matches = False
                        break

            if matches and row["prepared_payload_json"] and row["prepared_audit_json"]:
                # ── C03: Isolate metadata decoding and R4-03 logical digest identity ──
                try:
                    payload_dict = json.loads(row["prepared_payload_json"])
                    audit_dict = json.loads(row["prepared_audit_json"])
                    if not isinstance(payload_dict, dict) or not isinstance(audit_dict, dict):
                        raise ValueError("payload and audit must be dicts")
                except Exception:
                    conn.execute(
                        text("UPDATE experiment_publications SET status = 'QUARANTINED', updated_at = :now WHERE generation_id = :gen_id"),
                        {"gen_id": gen_id, "now": now_str},
                    )
                    shutil.rmtree(staging_dir, ignore_errors=True)
                    recovered += 1
                    continue

                recomputed_digest = recompute_hash(payload_dict)
                if recomputed_digest != full_digest or full_digest[:24] != exp_id:
                    # Digest/identity mismatch: quarantine without creating result rows
                    conn.execute(
                        text("UPDATE experiment_publications SET status = 'QUARANTINED', updated_at = :now WHERE generation_id = :gen_id"),
                        {"gen_id": gen_id, "now": now_str},
                    )
                    shutil.rmtree(staging_dir, ignore_errors=True)
                    recovered += 1
                    continue

                content_hashes = canonical_content_hashes(manifest, full_digest)

                # ── R4-02: SAVEPOINT so rejected transitions roll back result rows ──
                conn.execute(text("SAVEPOINT sp_recovery"))
                try:
                    # Unified validation and insertion (within savepoint)
                    repo._validate_and_insert_experiment_and_execution(
                        connection=conn,
                        experiment_id=exp_id,
                        deterministic_payload=payload_dict,
                        content_hashes=content_hashes,
                        execution_id=exec_id,
                        audit_metadata=audit_dict,
                    )

                    # If job_id exists, atomically transition the job to completed
                    if job_id and job_row:
                        res = conn.execute(
                            text("""
                                UPDATE jobs SET
                                    status = 'completed',
                                    experiment_id = :exp_id,
                                    result_json = :result_json,
                                    completed_at = :now
                                WHERE id = :job_id
                                  AND fencing_token = :fencing_token
                                  AND attempt = :attempt
                                  AND status IN ('running', 'claimed')
                                  AND cancel_requested = :not_cancelled
                            """),
                            {
                                "job_id": job_id,
                                "exp_id": exp_id,
                                "result_json": json.dumps({"experiment_id": exp_id, "recovered": True}),
                                "fencing_token": pub_fencing_token or job_row["fencing_token"],
                                "attempt": pub_attempt or job_row["attempt"],
                                "now": now_str,
                                "not_cancelled": False,
                            },
                        )
                        if res.rowcount == 0:
                            # Job transition rejected: roll back ALL result/audit rows
                            conn.execute(text("ROLLBACK TO SAVEPOINT sp_recovery"))
                            # Quarantine outside the savepoint
                            conn.execute(
                                text("UPDATE experiment_publications SET status = 'QUARANTINED', updated_at = :now WHERE generation_id = :gen_id"),
                                {"gen_id": gen_id, "now": now_str},
                            )
                            shutil.rmtree(staging_dir, ignore_errors=True)
                            recovered += 1
                            continue

                        # Emit completed job event
                        conn.execute(
                            text("""
                                INSERT INTO job_events (job_id, event_type, fencing_token, details_json, created_at)
                                VALUES (:job_id, 'completed', :fencing_token, :details_json, :created_at)
                            """),
                            {
                                "job_id": job_id,
                                "fencing_token": pub_fencing_token or job_row["fencing_token"],
                                "details_json": json.dumps({"experiment_id": exp_id, "recovery": True}),
                                "created_at": now_str,
                            },
                        )

                    # Mark publication as PUBLISHED
                    pub_res = conn.execute(
                        text("UPDATE experiment_publications SET status = 'PUBLISHED', updated_at = :now WHERE generation_id = :gen_id AND status = 'PREPARED'"),
                        {"gen_id": gen_id, "now": now_str},
                    )
                    if pub_res.rowcount == 0:
                        # Publication ownership lost: roll back result rows
                        conn.execute(text("ROLLBACK TO SAVEPOINT sp_recovery"))
                        recovered += 1
                        continue

                    # Success: release savepoint
                    conn.execute(text("RELEASE SAVEPOINT sp_recovery"))
                    shutil.rmtree(staging_dir, ignore_errors=True)
                    recovered += 1

                except Exception:
                    # Invariant mismatch or validation failure: roll back then quarantine
                    conn.execute(text("ROLLBACK TO SAVEPOINT sp_recovery"))
                    conn.execute(
                        text("UPDATE experiment_publications SET status = 'QUARANTINED', updated_at = :now WHERE generation_id = :gen_id"),
                        {"gen_id": gen_id, "now": now_str},
                    )
                    shutil.rmtree(staging_dir, ignore_errors=True)
                    recovered += 1
            else:
                conn.execute(
                    text("UPDATE experiment_publications SET status = 'QUARANTINED', updated_at = :now WHERE generation_id = :gen_id"),
                    {"gen_id": gen_id, "now": now_str},
                )
                shutil.rmtree(staging_dir, ignore_errors=True)
                recovered += 1

    return recovered


def cleanup_abandoned_staging(
    artifact_root: Path,
    queue_or_engine: Any | None = None,
    max_age_seconds: int = 3600,
) -> int:
    """Remove abandoned staging directories older than max_age_seconds, strictly protecting active work."""
    staging_root = artifact_root / ".staging"
    if not staging_root.is_dir():
        return 0

    active_generation_ids: set[str] = set()
    if queue_or_engine is not None:
        engine = getattr(queue_or_engine, "engine", queue_or_engine)
        try:
            with engine.connect() as conn:
                # Protect any generation currently in PREPARED state
                rows = conn.execute(text("SELECT generation_id FROM experiment_publications WHERE status = 'PREPARED'")).fetchall()
                active_generation_ids.update(row[0] for row in rows)
                # Protect staging associated with active running or claimed jobs
                active_job_gens = conn.execute(
                    text("""
                        SELECT generation_id FROM experiment_publications
                        WHERE job_id IN (SELECT id FROM jobs WHERE status IN ('claimed', 'running'))
                    """)
                ).fetchall()
                active_generation_ids.update(row[0] for row in active_job_gens)
                job_rows = conn.execute(text("SELECT id FROM jobs WHERE status IN ('claimed', 'running')")).fetchall()
                active_generation_ids.update(row[0] for row in job_rows)
        except Exception:
            pass

    now = time.time()
    cleaned = 0
    for item in staging_root.iterdir():
        if item.is_dir():
            # Never clean up directories belonging to active publications or running jobs
            if item.name in active_generation_ids:
                continue
            try:
                mtime = item.stat().st_mtime
                if (now - mtime) > max_age_seconds:
                    shutil.rmtree(item, ignore_errors=True)
                    cleaned += 1
            except OSError:
                pass
    return cleaned
 
 
def run_recovery_cycle(queue_or_engine: Any, artifact_root: Path) -> dict[str, int]:
    """Execute one full pass of publication recovery, lease recovery, and staging cleanup.

    R4-02 ordering fix: recover prepared publications FIRST while their associated
    jobs are still in 'running' state, THEN requeue expired leases.  The previous
    ordering requeued jobs first, which caused publication recovery to find already-
    requeued jobs and reject the completion transition while leaving orphaned
    experiment/execution rows.
    """
    pubs = recover_prepared_publications(queue_or_engine, artifact_root)
    leases = recover_expired_leases(queue_or_engine)
    staging = cleanup_abandoned_staging(artifact_root, queue_or_engine)
    return {"leases": leases, "publications": pubs, "staging": staging}


def run_recovery_loop(
    queue_or_engine: Any,
    artifact_root: Path,
    stop_event: threading.Event,
    interval: float = 5.0,
) -> None:
    """Run periodic recovery in background thread until stop_event is set."""
    while not stop_event.is_set():
        try:
            run_recovery_cycle(queue_or_engine, artifact_root)
        except Exception:
            pass
        stop_event.wait(interval)
