from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch
import pytest

from shiftguard.experiments.ids import stable_hash
from shiftguard.experiments.publication import PublicationService
from shiftguard.storage.repositories import ExperimentRepository


def test_publication_protocol_lifecycle_and_staging(tmp_path):
    """Verify PREPARED -> PUBLISHED lifecycle and that staging cleans up."""
    artifact_root = tmp_path / "artifacts"
    db_url = f"sqlite:///{tmp_path / 'pub.db'}"

    payload = {"experiment": "exp-1", "value": 42}
    files = {"config.json": {"a": 1}, "seeds.json": {"b": 2}}
    exec_id = "exec-uuid-1"
    audit = {"exec": exec_id, "timestamp": "2026-09-17T00:00:00Z"}

    exp_id, gen_id, hashes, target_dir = PublicationService.publish(
        artifact_root=artifact_root,
        deterministic_payload=payload,
        artifact_files=files,
        execution_id=exec_id,
        audit_metadata=audit,
        database_url=db_url,
    )

    assert target_dir.is_dir()
    assert (target_dir / "config.json").is_file()
    assert (target_dir / "seeds.json").is_file()
    # Staging directory must be cleaned up
    assert not (artifact_root / ".staging" / gen_id).exists()

    # Verify repository publication record
    repo = ExperimentRepository.from_url(db_url)
    try:
        pub = repo.get_publication(gen_id)
        assert pub is not None
        assert pub.status == "PUBLISHED"
        assert pub.experiment_id == exp_id
        assert "config.json" in pub.manifest
        assert "seeds.json" in pub.manifest

        stored = repo.get(exp_id)
        assert stored.experiment_id == exp_id
        assert repo.execution_ids(exp_id) == (exec_id,)
    finally:
        repo.dispose()


def test_failure_before_commit_leaves_no_target_directory(tmp_path):
    """A02 regression: Injected error before publication rename must leave no target artifact directory."""
    artifact_root = tmp_path / "artifacts"
    db_url = f"sqlite:///{tmp_path / 'pub_fail.db'}"

    payload = {"experiment": "fail-exp", "value": 99}
    files = {"config.json": {"x": 10}}
    exec_id = "exec-fail-1"
    audit = {"exec": exec_id}

    # Inject failure during reserve_publication
    with patch.object(ExperimentRepository, "reserve_publication", side_effect=RuntimeError("injected db error")):
        with pytest.raises(RuntimeError, match="injected db error"):
            PublicationService.publish(
                artifact_root=artifact_root,
                deterministic_payload=payload,
                artifact_files=files,
                execution_id=exec_id,
                audit_metadata=audit,
                database_url=db_url,
            )

    expected_exp_id = stable_hash(payload)[:24]
    target_dir = artifact_root / expected_exp_id
    # Target directory must NOT exist
    assert not target_dir.exists()


def test_reject_overwrite_of_existing_accepted_directory_with_conflict(tmp_path):
    """A02 regression: Existing accepted artifact directory cannot be corrupted by conflicting publication."""
    artifact_root = tmp_path / "artifacts"
    db_url = f"sqlite:///{tmp_path / 'pub_conflict.db'}"

    payload = {"experiment": "exp-immutable", "v": 1}
    files = {"config.json": {"version": 1}}
    exec_id_1 = "exec-1"

    exp_id, gen_id, hashes, target_dir = PublicationService.publish(
        artifact_root=artifact_root,
        deterministic_payload=payload,
        artifact_files=files,
        execution_id=exec_id_1,
        audit_metadata={"exec": exec_id_1},
        database_url=db_url,
    )

    # Manually tamper with the artifact on disk to simulate conflict
    config_file = target_dir / "config.json"
    original_bytes = config_file.read_bytes()
    config_file.write_bytes(b'{"tampered": true}\n')

    # Attempt second publication with original payload
    exec_id_2 = "exec-2"
    with pytest.raises(ValueError, match="refusing to overwrite"):
        PublicationService.publish(
            artifact_root=artifact_root,
            deterministic_payload=payload,
            artifact_files=files,
            execution_id=exec_id_2,
            audit_metadata={"exec": exec_id_2},
            database_url=db_url,
        )


def test_concurrent_insertion_and_replay_safety(tmp_path):
    """A03 regression: Conflict-safe insertion and UUID replay handling."""
    db_url = f"sqlite:///{tmp_path / 'race.db'}"
    repo = ExperimentRepository.from_url(db_url)

    exp_id = "exp-race-1"
    payload = {"race": True}
    hashes = {"config": "hash-1"}

    # First insert
    repo.put(exp_id, payload, hashes, "exec-1", {"worker": "A"})
    assert repo.execution_ids(exp_id) == ("exec-1",)

    # Second concurrent insert with same experiment_id and distinct execution_id
    repo.put(exp_id, payload, hashes, "exec-2", {"worker": "B"})
    assert sorted(repo.execution_ids(exp_id)) == ["exec-1", "exec-2"]

    # Idempotent replay with same execution_id and identical audit
    repo.put(exp_id, payload, hashes, "exec-1", {"worker": "A"})
    assert sorted(repo.execution_ids(exp_id)) == ["exec-1", "exec-2"]

    # Replay with same execution_id but different audit must be rejected
    with pytest.raises(ValueError, match="already exists with different audit"):
        repo.put(exp_id, payload, hashes, "exec-1", {"worker": "MUTATED"})

    # Conflict with differing experiment content must be rejected
    with pytest.raises(ValueError, match="immutable and does not match"):
        repo.put(exp_id, {"race": False}, hashes, "exec-3", {"worker": "C"})

    repo.dispose()
