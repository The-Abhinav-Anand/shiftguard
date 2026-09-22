from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

from dataclasses import dataclass

from sqlalchemy import Engine, text
from sqlalchemy.engine import make_url

from shiftguard.experiments.ids import stable_hash
from shiftguard.jobs.models import (
    PublicationContentionError,
    PublicationLostOwnershipError,
    WorkerCancelledException,
    WorkerFencedOutException,
)
from shiftguard.migrations import upgrade_database
from shiftguard.settings import Settings
from shiftguard.storage.db import create_engine_for_settings


class ExperimentImmutabilityError(ValueError):
    """Raised when an experiment content violates immutability invariants."""
    pass


def canonical_content_hashes(manifest: dict[str, str], logical_content: str) -> dict[str, str]:
    """Compute canonical content_hashes dictionary from artifact manifest and full logical content hash.
    
    Keys are file stems (e.g. 'result.json' -> 'result', 'payloads/budget_curve.json' -> 'budget_curve'),
    plus the required 'logical_content' key.
    """
    hashes = {Path(rel_path).stem: h for rel_path, h in manifest.items()}
    hashes["logical_content"] = logical_content
    return hashes


@dataclass(frozen=True)
class StoredExperiment:
    experiment_id: str
    content_hashes: dict[str, str]
    deterministic_payload: dict[str, object]


@dataclass(frozen=True)
class PublicationRecord:
    generation_id: str
    experiment_id: str
    full_digest: str
    execution_id: str
    status: str
    manifest: dict[str, str]
    created_at: str
    updated_at: str
    job_id: str | None = None
    lease_expires_at: str | None = None
    attempt: int | None = None
    fencing_token: str | None = None


class ExperimentRepository:
    def __init__(self, engine: Engine, environment: str | None = None, settings: Settings | None = None) -> None:
        self.engine = engine
        self.environment = environment
        self.settings = settings

    @classmethod
    def from_url(cls, database_url: str, environment: str | None = None) -> ExperimentRepository:
        if environment:
            settings = Settings(SHIFTGUARD_DB_URL=database_url, SHIFTGUARD_ENVIRONMENT=environment)
        else:
            url = make_url(database_url)
            if url.drivername.startswith("postgresql"):
                settings = Settings(SHIFTGUARD_DB_URL=database_url, SHIFTGUARD_ENVIRONMENT="hosted")
            else:
                settings = Settings(SHIFTGUARD_DB_URL=database_url)
        upgrade_database(settings)
        return cls(create_engine_for_settings(settings), environment=settings.environment, settings=settings)

    @classmethod
    def from_settings(cls, settings: Settings) -> ExperimentRepository:
        upgrade_database(settings)
        return cls(create_engine_for_settings(settings), environment=settings.environment, settings=settings)

    def _validate_and_insert_experiment_and_execution(
        self,
        connection: Any,
        experiment_id: str,
        deterministic_payload: dict[str, Any],
        content_hashes: dict[str, str],
        execution_id: str,
        audit_metadata: dict[str, Any],
    ) -> None:
        """Enforce identical experiment and execution immutability invariants across normal and recovery paths.

        Uses targeted ON CONFLICT (pk) DO NOTHING to avoid races between concurrent
        connections that both observe absence.  After the conflict-safe INSERT, the
        winning row is read back and its content is compared; true mismatches still
        raise ExperimentImmutabilityError / ValueError.
        """
        payload_json = json.dumps(deterministic_payload, sort_keys=True, separators=(",", ":"))
        hashes_json = json.dumps(content_hashes, sort_keys=True, separators=(",", ":"))
        audit_json = json.dumps(audit_metadata, sort_keys=True, separators=(",", ":"))

        # 1. Experiments row: conflict-safe insert then verify immutability
        connection.execute(
            text(
                "INSERT INTO experiments (id, payload_json, content_hashes_json) "
                "VALUES (:id, :payload, :hashes) "
                "ON CONFLICT (id) DO NOTHING"
            ),
            {"id": experiment_id, "payload": payload_json, "hashes": hashes_json},
        )
        stored_exp = connection.execute(
            text("SELECT payload_json, content_hashes_json FROM experiments WHERE id = :id"),
            {"id": experiment_id},
        ).one()
        if stored_exp[0] != payload_json or stored_exp[1] != hashes_json:
            raise ExperimentImmutabilityError(
                "existing experiment content is immutable and does not match this execution"
            )

        # 2. Experiment executions row: conflict-safe insert then verify immutability
        connection.execute(
            text(
                "INSERT INTO experiment_executions (execution_id, experiment_id, audit_json) "
                "VALUES (:execution_id, :experiment_id, :audit) "
                "ON CONFLICT (execution_id) DO NOTHING"
            ),
            {"execution_id": execution_id, "experiment_id": experiment_id, "audit": audit_json},
        )
        stored_exec = connection.execute(
            text("SELECT experiment_id, audit_json FROM experiment_executions WHERE execution_id = :execution_id"),
            {"execution_id": execution_id},
        ).one()
        if stored_exec[0] != experiment_id or stored_exec[1] != audit_json:
            raise ValueError(
                f"execution_id {execution_id} already exists with different audit or experiment_id"
            )

    def put(
        self,
        experiment_id: str,
        deterministic_payload: dict[str, object],
        content_hashes: dict[str, str],
        execution_id: str,
        audit_metadata: dict[str, object],
        generation_id: str | None = None,
        job_context: tuple[str, str] | None = None,  # (job_id, fencing_token)
    ) -> None:
        with self.engine.begin() as connection:
            # 1. If job_context is supplied, atomically lock and verify job state on PostgreSQL
            if job_context and connection.dialect.name == "postgresql":
                job_id, _ = job_context
                connection.execute(
                    text("SELECT id FROM jobs WHERE id = :job_id FOR UPDATE"),
                    {"job_id": job_id},
                )

            transition_time = datetime.now(timezone.utc).isoformat()

            # 2. Strict ownership validation if publishing a staged generation
            pub_row = None
            if generation_id:
                pub_row = connection.execute(
                    text("""
                        SELECT generation_id, status, experiment_id, full_digest, execution_id,
                               job_id, lease_expires_at, attempt, fencing_token,
                               prepared_payload_json, prepared_audit_json
                        FROM experiment_publications
                        WHERE generation_id = :gen_id
                    """),
                    {"gen_id": generation_id},
                ).mappings().fetchone()

                if not pub_row:
                    raise PublicationLostOwnershipError(
                        f"Generation '{generation_id}' not found in experiment_publications"
                    )
                if pub_row["status"] != "PREPARED":
                    raise PublicationLostOwnershipError(
                        f"Generation '{generation_id}' lost publication ownership: status is '{pub_row['status']}', expected 'PREPARED'"
                    )
                if pub_row["experiment_id"] != experiment_id or pub_row["execution_id"] != execution_id:
                    raise PublicationLostOwnershipError(
                        f"Generation '{generation_id}' identity mismatch: expected ({pub_row['experiment_id']}, {pub_row['execution_id']}), got ({experiment_id}, {execution_id})"
                    )

                # ── Content identity validation (R6-03 / I05) ──
                if "logical_content" not in content_hashes:
                    raise PublicationLostOwnershipError(
                        f"Generation '{generation_id}' staged finalization requires 'logical_content' in content_hashes"
                    )
                caller_logical = content_hashes["logical_content"]
                if pub_row["full_digest"] != caller_logical:
                    raise PublicationLostOwnershipError(
                        f"Generation '{generation_id}' full digest mismatch: expected '{pub_row['full_digest']}', got '{caller_logical}'"
                    )
                if caller_logical[:24] != experiment_id:
                    raise PublicationLostOwnershipError(
                        f"Generation '{generation_id}' logical content prefix '{caller_logical[:24]}' does not match experiment_id '{experiment_id}'"
                    )
                recomputed_digest = stable_hash(deterministic_payload)
                if recomputed_digest != caller_logical:
                    raise PublicationLostOwnershipError(
                        f"Generation '{generation_id}' deterministic payload digest '{recomputed_digest}' does not match logical_content '{caller_logical}'"
                    )
                if recomputed_digest[:24] != experiment_id:
                    raise PublicationLostOwnershipError(
                        f"Generation '{generation_id}' payload digest prefix '{recomputed_digest[:24]}' does not match experiment_id '{experiment_id}'"
                    )
                if pub_row["prepared_payload_json"] is not None:
                    if stable_hash(json.loads(pub_row["prepared_payload_json"])) != recomputed_digest:
                        raise PublicationLostOwnershipError(
                            f"Generation '{generation_id}' payload mismatch with prepared publication"
                        )

                # ── Worker authority validation (R6-03 / I05) ──
                if job_context:
                    caller_job_id, caller_fencing_token = job_context
                    if pub_row["job_id"] is None or pub_row["attempt"] is None or pub_row["fencing_token"] is None:
                        raise PublicationLostOwnershipError(
                            f"Generation '{generation_id}' has incomplete worker reservation metadata "
                            f"(job_id={pub_row['job_id']}, attempt={pub_row['attempt']}, fencing_token={pub_row['fencing_token']})"
                        )
                    if pub_row["job_id"] != caller_job_id:
                        raise PublicationLostOwnershipError(
                            f"Generation '{generation_id}' belongs to job '{pub_row['job_id']}', not caller '{caller_job_id}'"
                        )
                    if pub_row["fencing_token"] != caller_fencing_token:
                        raise PublicationLostOwnershipError(
                            f"Generation '{generation_id}' was prepared with fencing token '{pub_row['fencing_token']}', not caller '{caller_fencing_token}'"
                        )

                    j_check = connection.execute(
                        text("SELECT attempt, fencing_token, status, cancel_requested, lease_expires_at FROM jobs WHERE id = :job_id"),
                        {"job_id": caller_job_id},
                    ).mappings().fetchone()
                    if not j_check:
                        raise PublicationLostOwnershipError(f"Owning job '{caller_job_id}' not found")
                    if j_check["cancel_requested"]:
                        raise WorkerCancelledException(f"Job '{caller_job_id}' was cancelled during publication")
                    if pub_row["attempt"] != j_check["attempt"]:
                        raise PublicationLostOwnershipError(
                            f"Generation '{generation_id}' was prepared for attempt {pub_row['attempt']}, but current job attempt is {j_check['attempt']}"
                        )
                    if pub_row["fencing_token"] != j_check["fencing_token"]:
                        raise PublicationLostOwnershipError(
                            f"Generation '{generation_id}' fencing token does not match active job fencing token"
                        )
                else:
                    if pub_row["job_id"] is not None or pub_row["attempt"] is not None or pub_row["fencing_token"] is not None:
                        raise PublicationLostOwnershipError(
                            f"Generation '{generation_id}' was reserved with worker metadata but caller provided no job context"
                        )

            # 3. Unified validation and insertion of experiment and execution records
            self._validate_and_insert_experiment_and_execution(
                connection=connection,
                experiment_id=experiment_id,
                deterministic_payload=deterministic_payload,
                content_hashes=content_hashes,
                execution_id=execution_id,
                audit_metadata=audit_metadata,
            )

            # 4. Atomically finalize publication conditionally on PREPARED state and matching identity
            if generation_id and pub_row:
                update_params: dict[str, Any] = {
                    "gen_id": generation_id,
                    "exp_id": experiment_id,
                    "exec_id": execution_id,
                    "updated": transition_time,
                }
                where_clauses = [
                    "generation_id = :gen_id",
                    "status = 'PREPARED'",
                    "experiment_id = :exp_id",
                    "execution_id = :exec_id",
                ]
                if job_context:
                    where_clauses.append("job_id = :job_id")
                    update_params["job_id"] = pub_row["job_id"]
                    where_clauses.append("fencing_token = :fencing_token")
                    update_params["fencing_token"] = pub_row["fencing_token"]
                    where_clauses.append("attempt = :attempt")
                    update_params["attempt"] = pub_row["attempt"]
                else:
                    where_clauses.append("job_id IS NULL")
                    where_clauses.append("fencing_token IS NULL")
                    where_clauses.append("attempt IS NULL")

                pub_res = connection.execute(
                    text(f"UPDATE experiment_publications SET status = 'PUBLISHED', updated_at = :updated WHERE {' AND '.join(where_clauses)}"),
                    update_params,
                )
                if pub_res.rowcount == 0:
                    raise PublicationLostOwnershipError(
                        f"Generation '{generation_id}' lost publication ownership or was not in PREPARED state for experiment '{experiment_id}'"
                    )

            # 4. Atomically complete the job in the EXACT SAME transaction checking unexpired lease AT TRANSITION TIME
            if job_context:
                job_id, fencing_token = job_context
                result_json = json.dumps({"experiment_id": experiment_id, "completed_at": transition_time})
                job_update = connection.execute(
                    text("""
                        UPDATE jobs SET
                            status = 'completed',
                            experiment_id = :exp_id,
                            result_json = :result_json,
                            completed_at = :completed_at
                        WHERE id = :job_id
                          AND fencing_token = :fencing_token
                          AND status = 'running'
                          AND cancel_requested = :not_cancelled
                          AND lease_expires_at IS NOT NULL
                          AND lease_expires_at >= :current_time
                    """),
                    {
                        "job_id": job_id,
                        "fencing_token": fencing_token,
                        "exp_id": experiment_id,
                        "result_json": result_json,
                        "completed_at": transition_time,
                        "not_cancelled": False,
                        "current_time": transition_time,
                    },
                )
                if job_update.rowcount == 0:
                    # Diagnose cause: cancellation vs fencing/lease expiry
                    j_check = connection.execute(
                        text("SELECT status, cancel_requested, lease_expires_at, fencing_token FROM jobs WHERE id = :job_id"),
                        {"job_id": job_id},
                    ).mappings().fetchone()
                    if j_check and j_check["cancel_requested"]:
                        raise WorkerCancelledException(f"Job '{job_id}' was cancelled during publication")
                    raise WorkerFencedOutException(f"Job '{job_id}' completion update failed: lease expired or worker fenced out")

                connection.execute(
                    text("""
                        INSERT INTO job_events (job_id, event_type, fencing_token, details_json, created_at)
                        VALUES (:job_id, 'completed', :fencing_token, :details_json, :created_at)
                    """),
                    {
                        "job_id": job_id,
                        "fencing_token": fencing_token,
                        "details_json": json.dumps({"experiment_id": experiment_id}),
                        "created_at": transition_time,
                    },
                )

    def reserve_publication(
        self,
        generation_id: str,
        experiment_id: str,
        full_digest: str,
        execution_id: str,
        manifest: dict[str, str],
        job_id: str | None = None,
        lease_expires_at: str | None = None,
        prepared_payload: dict[str, object] | None = None,
        prepared_audit: dict[str, object] | None = None,
        attempt: int | None = None,
        fencing_token: str | None = None,
    ) -> None:
        manifest_json = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
        payload_json = json.dumps(prepared_payload, sort_keys=True, separators=(",", ":")) if prepared_payload is not None else None
        audit_json = json.dumps(prepared_audit, sort_keys=True, separators=(",", ":")) if prepared_audit is not None else None

        with self.engine.begin() as connection:
            # Lock before reading even when no publication row exists yet. A row
            # lock alone cannot serialize the first reservation for an experiment.
            if connection.dialect.name == "sqlite":
                connection.execute(text("BEGIN IMMEDIATE"))
            elif connection.dialect.name == "postgresql":
                lock_key = int.from_bytes(
                    hashlib.sha256(("shiftguard:publication:" + experiment_id).encode()).digest()[:8],
                    byteorder="big", signed=True,
                )
                connection.execute(
                    text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key}
                )
            # Time spent waiting for ownership must not consume the new lease or
            # make the existing owner's expiry check use a stale timestamp.
            now = datetime.now(timezone.utc)
            now_str = now.isoformat()
            if not lease_expires_at:
                lease_expires_at = (now + timedelta(seconds=120)).isoformat()

            # Check for existing PUBLISHED experiment
            published = connection.execute(
                text(
                    "SELECT manifest_json FROM experiment_publications "
                    "WHERE experiment_id = :exp_id AND status = 'PUBLISHED' LIMIT 1"
                ),
                {"exp_id": experiment_id},
            ).mappings().fetchone()
            if published:
                pub_manifest = json.loads(published["manifest_json"])
                if pub_manifest != manifest:
                    raise ValueError(
                        f"Experiment '{experiment_id}' is already PUBLISHED with a different manifest"
                    )

            # Check if an existing PREPARED generation is currently held by an active live owner (job or CLI)
            prepared_rows = connection.execute(
                text(
                    "SELECT generation_id, job_id, lease_expires_at FROM experiment_publications "
                    "WHERE experiment_id = :exp_id AND status = 'PREPARED'"
                ),
                {"exp_id": experiment_id},
            ).mappings().fetchall()

            for p_row in prepared_rows:
                p_job_id = p_row["job_id"]
                p_lease_exp = p_row["lease_expires_at"]

                if p_job_id:
                    job_sql = "SELECT status, cancel_requested, lease_expires_at FROM jobs WHERE id = :job_id"
                    if connection.dialect.name == "postgresql":
                        job_sql += " FOR UPDATE"
                    j_row = connection.execute(text(job_sql), {"job_id": p_job_id}).mappings().fetchone()
                    # Heartbeats extend the worker lease, not the publication's
                    # original deadline. The worker's current lease is authoritative.
                    if (j_row and j_row["status"] in ("running", "claimed")
                            and not j_row["cancel_requested"] and j_row["lease_expires_at"]
                            and j_row["lease_expires_at"] > datetime.now(timezone.utc).isoformat()):
                        raise PublicationContentionError(
                            f"Experiment '{experiment_id}' is currently being published by active job '{p_job_id}' (generation '{p_row['generation_id']}')"
                        )
                elif p_lease_exp and p_lease_exp > now_str:
                    raise PublicationContentionError(
                        f"Experiment '{experiment_id}' is currently being published by active CLI owner (generation '{p_row['generation_id']}', lease until {p_lease_exp})"
                    )

            # Only mark existing demonstrably expired/stale PREPARED generations as ABANDONED
            connection.execute(
                text(
                    "UPDATE experiment_publications "
                    "SET status = 'ABANDONED', updated_at = :updated "
                    "WHERE experiment_id = :exp_id AND status = 'PREPARED'"
                ),
                {"exp_id": experiment_id, "updated": now_str},
            )

            connection.execute(
                text(
                    "INSERT INTO experiment_publications "
                    "(generation_id, experiment_id, full_digest, execution_id, status, manifest_json, job_id, lease_expires_at, prepared_payload_json, prepared_audit_json, attempt, fencing_token, created_at, updated_at) "
                    "VALUES (:gen_id, :exp_id, :digest, :exec_id, 'PREPARED', :manifest, :job_id, :lease_expires_at, :prepared_payload, :prepared_audit, :attempt, :fencing_token, :created, :updated)"
                ),
                {
                    "gen_id": generation_id,
                    "exp_id": experiment_id,
                    "digest": full_digest,
                    "exec_id": execution_id,
                    "manifest": manifest_json,
                    "job_id": job_id,
                    "lease_expires_at": lease_expires_at,
                    "prepared_payload": payload_json,
                    "prepared_audit": audit_json,
                    "attempt": attempt,
                    "fencing_token": fencing_token,
                    "created": now_str,
                    "updated": now_str,
                },
            )


    def quarantine_publication(self, generation_id: str) -> None:
        now_str = datetime.now(timezone.utc).isoformat()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE experiment_publications "
                    "SET status = 'QUARANTINED', updated_at = :updated "
                    "WHERE generation_id = :gen_id"
                ),
                {"gen_id": generation_id, "updated": now_str},
            )

    def get_publication(self, generation_id: str) -> PublicationRecord | None:
        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT generation_id, experiment_id, full_digest, execution_id, status, manifest_json, created_at, updated_at, job_id, lease_expires_at, attempt, fencing_token "
                    "FROM experiment_publications WHERE generation_id = :gen_id"
                ),
                {"gen_id": generation_id},
            ).mappings().one_or_none()
        if row is None:
            return None
        return PublicationRecord(
            generation_id=row["generation_id"],
            experiment_id=row["experiment_id"],
            full_digest=row["full_digest"],
            execution_id=row["execution_id"],
            status=row["status"],
            manifest=json.loads(row["manifest_json"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            job_id=row.get("job_id"),
            lease_expires_at=row.get("lease_expires_at"),
            attempt=row.get("attempt"),
            fencing_token=row.get("fencing_token"),
        )

    def get_published_experiment(self, experiment_id: str) -> PublicationRecord | None:
        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT generation_id, experiment_id, full_digest, execution_id, status, manifest_json, created_at, updated_at, job_id, lease_expires_at, attempt, fencing_token "
                    "FROM experiment_publications "
                    "WHERE experiment_id = :exp_id AND status = 'PUBLISHED' "
                    "ORDER BY updated_at DESC LIMIT 1"
                ),
                {"exp_id": experiment_id},
            ).mappings().one_or_none()
        if row is None:
            return None
        return PublicationRecord(
            generation_id=row["generation_id"],
            experiment_id=row["experiment_id"],
            full_digest=row["full_digest"],
            execution_id=row["execution_id"],
            status=row["status"],
            manifest=json.loads(row["manifest_json"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            job_id=row.get("job_id"),
            lease_expires_at=row.get("lease_expires_at"),
            attempt=row.get("attempt"),
            fencing_token=row.get("fencing_token"),
        )

    def get_published(self, experiment_id: str) -> tuple[StoredExperiment, PublicationRecord] | None:
        """Retrieve stored experiment and its verified PUBLISHED record."""
        with self.engine.connect() as connection:
            pub_row = connection.execute(
                text(
                    "SELECT generation_id, experiment_id, full_digest, execution_id, status, manifest_json, created_at, updated_at "
                    "FROM experiment_publications "
                    "WHERE experiment_id = :exp_id AND status = 'PUBLISHED' "
                    "ORDER BY updated_at DESC LIMIT 1"
                ),
                {"exp_id": experiment_id},
            ).one_or_none()
            if pub_row is None:
                return None

            exp_row = connection.execute(
                text("SELECT content_hashes_json, payload_json FROM experiments WHERE id = :id"),
                {"id": experiment_id},
            ).one_or_none()
            if exp_row is None:
                return None

            stored_exp = StoredExperiment(
                experiment_id=experiment_id,
                content_hashes=json.loads(exp_row[0]),
                deterministic_payload=json.loads(exp_row[1]),
            )
            pub_rec = PublicationRecord(
                generation_id=pub_row[0],
                experiment_id=pub_row[1],
                full_digest=pub_row[2],
                execution_id=pub_row[3],
                status=pub_row[4],
                manifest=json.loads(pub_row[5]),
                created_at=pub_row[6],
                updated_at=pub_row[7],
            )
            return stored_exp, pub_rec

    def list_published(self, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
        """List experiments that have a verified PUBLISHED publication record.
        
        Aggregates by experiment ID to deduplicate identical republish runs.
        """
        with self.engine.connect() as connection:
            rows = connection.execute(
                text("""
                    SELECT e.id, MAX(p.created_at) AS latest_published_at
                    FROM experiments e
                    JOIN experiment_publications p ON e.id = p.experiment_id
                    WHERE p.status = 'PUBLISHED'
                    GROUP BY e.id
                    ORDER BY latest_published_at DESC, e.id ASC
                    LIMIT :limit OFFSET :offset
                """),
                {"limit": limit, "offset": offset},
            ).fetchall()
        return [{"experiment_id": row[0], "created_at": row[1]} for row in rows]

    def get(self, experiment_id: str) -> StoredExperiment | None:
        with self.engine.connect() as connection:
            row = connection.execute(
                text("SELECT content_hashes_json, payload_json FROM experiments WHERE id = :id"),
                {"id": experiment_id},
            ).fetchone()
        if not row:
            return None
        return StoredExperiment(
            experiment_id=experiment_id,
            content_hashes=json.loads(row[0]),
            deterministic_payload=json.loads(row[1]),
        )

    def list(self, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                text("SELECT id FROM experiments ORDER BY id ASC LIMIT :limit OFFSET :offset"),
                {"limit": limit, "offset": offset},
            ).fetchall()
        return [{"experiment_id": row[0]} for row in rows]

    def execution_ids(self, experiment_id: str) -> tuple[str, ...]:
        with self.engine.connect() as connection:
            rows = connection.execute(text("SELECT execution_id FROM experiment_executions WHERE experiment_id = :id ORDER BY execution_id"), {"id": experiment_id}).all()
        return tuple(row[0] for row in rows)

    def dispose(self) -> None:
        self.engine.dispose()
