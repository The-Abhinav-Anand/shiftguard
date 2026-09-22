from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
from uuid import uuid4

from shiftguard.experiments.artifacts import write_json_artifact
from shiftguard.experiments.ids import stable_hash
from shiftguard.storage.repositories import ExperimentRepository


class PublicationService:
    @staticmethod
    def publish(
        artifact_root: Path,
        deterministic_payload: dict[str, object],
        artifact_files: dict[str, object],
        execution_id: str,
        audit_metadata: dict[str, object],
        database_url: str,
        is_cancelled: object | None = None,
        fencing_token: str | None = None,
        queue: object | None = None,
        job_id: str | None = None,
        attempt: int | None = None,
        settings: Any | None = None,
        environment: str | None = None,
    ) -> tuple[str, str, dict[str, str], Path]:
        """Execute recoverable two-phase publication protocol with safe-unit cancellation checks.

        Returns (experiment_id, generation_id, content_hashes, target_dir).
        """
        def _check_cancelled():
            if callable(is_cancelled) and is_cancelled():
                raise RuntimeError("Operation cancelled by user or cooperative worker check")
            if queue and job_id and fencing_token:
                if getattr(queue, "is_cancellation_requested", None) and queue.is_cancellation_requested(job_id, fencing_token):
                    raise RuntimeError("Operation cancelled: job cancellation requested")

        _check_cancelled()

        # Step 1: Compute deterministic experiment_id and logical_content
        logical_content = stable_hash(deterministic_payload)
        experiment_id = logical_content[:24]

        # Step 2: Private staging on the same filesystem
        generation_id = str(uuid4())
        staging_root = artifact_root / ".staging"
        staging_root.mkdir(parents=True, exist_ok=True)
        staging_dir = staging_root / generation_id
        staging_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Step 3: Write all files into private staging, calculate exact byte hashes
            manifest = {}
            content_hashes = {}
            for rel_path, content in artifact_files.items():
                dest_file = staging_dir / rel_path
                dest_dir = dest_file.parent
                dest_dir.mkdir(parents=True, exist_ok=True)
                file_hash = write_json_artifact(dest_dir, dest_file.name, content)
                manifest[rel_path] = file_hash

                # Map to content_hashes key (e.g. "config.json" -> "config", "payloads/budget_curve.json" -> "budget_curve")
                key_name = Path(rel_path).stem
                content_hashes[key_name] = file_hash
            content_hashes["logical_content"] = logical_content

            # Validate exact manifest against disk
            for rel_path, expected_hash in manifest.items():
                p = staging_dir / rel_path
                if not p.is_file():
                    raise RuntimeError(f"Staged artifact missing: {p}")
                actual_hash = hashlib.sha256(p.read_bytes()).hexdigest()
                if actual_hash != expected_hash:
                    raise RuntimeError(
                        f"Staged artifact hash mismatch for {rel_path}: {actual_hash} != {expected_hash}"
                    )

            _check_cancelled()

            # Step 4: In short DB transaction, reserve publication ownership (PREPARED)
            if settings is not None:
                repository = ExperimentRepository.from_settings(settings)
            elif environment is not None:
                repository = ExperimentRepository.from_url(database_url, environment=environment)
            else:
                repository = ExperimentRepository.from_url(database_url)
            try:
                repository.reserve_publication(
                    generation_id=generation_id,
                    experiment_id=experiment_id,
                    full_digest=logical_content,
                    execution_id=execution_id,
                    manifest=manifest,
                    job_id=job_id,
                    prepared_payload=deterministic_payload,
                    prepared_audit=audit_metadata,
                    attempt=attempt,
                    fencing_token=fencing_token,
                )

                _check_cancelled()

                # Step 5: Finalize directory with atomic rename or reuse matching accepted generation
                target_dir = artifact_root / experiment_id
                if target_dir.exists():
                    matches = True
                    for rel_path, expected_hash in manifest.items():
                        target_file = target_dir / rel_path
                        if (
                            not target_file.is_file()
                            or hashlib.sha256(target_file.read_bytes()).hexdigest() != expected_hash
                        ):
                            matches = False
                            break
                    if matches:
                        # Existing accepted generation matches manifest, reuse it without overwrite
                        shutil.rmtree(staging_dir, ignore_errors=True)
                    else:
                        repository.quarantine_publication(generation_id)
                        raise ValueError(
                            f"Existing artifact directory {target_dir} does not match expected manifest; refusing to overwrite"
                        )
                else:
                    # Atomic move into final location
                    try:
                        staging_dir.rename(target_dir)
                    except Exception:
                        os.replace(str(staging_dir), str(target_dir))

                _check_cancelled()

                # Step 6: In atomic single transaction, commit experiment and mark PUBLISHED
                job_context = (job_id, fencing_token) if job_id and fencing_token else None
                repository.put(
                    experiment_id=experiment_id,
                    deterministic_payload=deterministic_payload,
                    content_hashes=content_hashes,
                    execution_id=execution_id,
                    audit_metadata=audit_metadata,
                    generation_id=generation_id,
                    job_context=job_context,
                )

            except Exception:
                try:
                    repository.quarantine_publication(generation_id)
                except Exception:
                    pass
                raise
            finally:
                repository.dispose()

        finally:
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)

        return experiment_id, generation_id, content_hashes, target_dir
