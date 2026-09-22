"""Unit tests for Gate 4 publication concurrency, manifest-backed reads, and crash recovery."""

from __future__ import annotations

import json
from pathlib import Path
import threading
import pytest
from sqlalchemy import create_engine, text

from shiftguard.experiments.ids import stable_hash
from shiftguard.experiments.publication import PublicationService
from shiftguard.jobs.models import PublicationContentionError
from shiftguard.jobs.recovery import recover_prepared_publications
from shiftguard.migrations import upgrade_database
from shiftguard.settings import Settings
from shiftguard.storage.repositories import ExperimentRepository


@pytest.fixture
def pub_fixture(tmp_path):
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir(parents=True, exist_ok=True)
    db_file = tmp_path / "pub_concurrency.db"
    settings = Settings(SHIFTGUARD_DB_URL=f"sqlite:///{db_file}")
    upgrade_database(settings)
    engine = create_engine(f"sqlite:///{db_file}")
    try:
        yield engine, artifact_root, f"sqlite:///{db_file}"
    finally:
        engine.dispose()


def test_get_published_requires_published_status(pub_fixture):
    """G4-05: Experiment repository get_published and list_published strictly require status='PUBLISHED'."""
    engine, artifact_root, db_url = pub_fixture
    repo = ExperimentRepository(engine)

    payload = {"data": "test"}
    digest = stable_hash(payload)
    exp_id = digest[:24]
    hashes = {"config": "abc", "logical_content": digest}
    exec_id = "exec-1"

    # Insert into experiments and executions using repo.put (without generation_id)
    repo.put(exp_id, payload, hashes, exec_id, audit_metadata={"worker": "test"})

    # Readers retrieving via get_published and list_published must find nothing
    assert repo.get_published(exp_id) is None
    assert len(repo.list_published()) == 0

    # Now simulate atomic publication with generation_id
    gen_id = "gen-1"
    repo.reserve_publication(gen_id, exp_id, digest, exec_id, {"config.json": "abc"}, prepared_payload=payload)
    repo.put(exp_id, payload, hashes, exec_id, audit_metadata={"worker": "test"}, generation_id=gen_id)

    res = repo.get_published(exp_id)
    assert res is not None
    exp_rec, pub_rec = res
    assert exp_rec.experiment_id == exp_id
    assert pub_rec.status == "PUBLISHED"
    assert len(repo.list_published()) == 1


def test_competing_publication_reservations_are_serialized(pub_fixture):
    """G4-05: Simultaneous reserve_publication calls serialize cleanly."""
    engine, artifact_root, db_url = pub_fixture
    repo = ExperimentRepository(engine)

    exp_id = "exp-compete-1"
    manifest = {"config.json": "hash-1"}

    # Reserve first generation
    gen1 = "gen-compete-1"
    repo.reserve_publication(gen1, exp_id, "digest-1", "exec-1", manifest)
    pub1 = repo.get_publication(gen1)
    assert pub1.status == "PREPARED"

    # Reserve second competing generation while first generation is still active -> raises PublicationContentionError (R3-04)
    gen2 = "gen-compete-2"
    with pytest.raises(PublicationContentionError):
        repo.reserve_publication(gen2, exp_id, "digest-2", "exec-2", manifest)

    pub1_still_active = repo.get_publication(gen1)
    assert pub1_still_active.status == "PREPARED"

    # Once generation 1's lease expires, second reservation succeeds and gen1 becomes ABANDONED
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE experiment_publications SET lease_expires_at = '2026-09-17T00:00:00Z' WHERE generation_id = :gen1"),
            {"gen1": gen1},
        )

    repo.reserve_publication(gen2, exp_id, "digest-2", "exec-2", manifest)
    pub2 = repo.get_publication(gen2)
    assert pub2.status == "PREPARED"

    # Stale generation 1 must now be ABANDONED in DB
    pub1_stale = repo.get_publication(gen1)
    assert pub1_stale.status == "ABANDONED"


def test_prepared_publication_crash_recovery(pub_fixture):
    """G4-03 / G4-05: recover_prepared_publications recovers complete directories and quarantines broken ones."""
    engine, artifact_root, db_url = pub_fixture
    import hashlib

    # Case 1: Complete artifact directory matches manifest -> recovers to PUBLISHED
    payload_dict = {"data": "recovered_payload"}
    full_digest1 = stable_hash(payload_dict)
    exp1 = full_digest1[:24]
    gen1 = "gen-rec-1"
    dir1 = artifact_root / exp1
    dir1.mkdir(parents=True, exist_ok=True)
    f1 = dir1 / "result.json"
    f1_bytes = b'{"status": "recovered"}'
    f1.write_bytes(f1_bytes)
    h1 = hashlib.sha256(f1_bytes).hexdigest()
    manifest1 = {"result.json": h1}

    # Case 2: Incomplete directory (missing file) -> recovers to QUARANTINED
    exp2 = "exp-recover-bad"
    gen2 = "gen-rec-2"
    dir2 = artifact_root / exp2
    dir2.mkdir(parents=True, exist_ok=True)
    # File not created on disk
    manifest2 = {"missing.json": "somehash"}

    payload1 = json.dumps(payload_dict)
    audit1 = json.dumps({"worker": "recovered_worker"})

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO experiment_publications (
                    generation_id, experiment_id, status, full_digest, execution_id, manifest_json,
                    prepared_payload_json, prepared_audit_json, created_at, updated_at
                )
                VALUES (
                    :gen_id, :exp_id, 'PREPARED', :full_digest, 'exec-dummy', :man,
                    :payload, :audit, '2026-09-17T00:00:00Z', '2026-09-17T00:00:00Z'
                )
            """),
            [
                {"gen_id": gen1, "exp_id": exp1, "full_digest": full_digest1, "man": json.dumps(manifest1), "payload": payload1, "audit": audit1},
                {"gen_id": gen2, "exp_id": exp2, "full_digest": "dig-bad", "man": json.dumps(manifest2), "payload": None, "audit": None},
            ],
        )

    # Run crash recovery
    recovered_count = recover_prepared_publications(engine, artifact_root)
    assert recovered_count == 2

    repo = ExperimentRepository(engine)
    pub1 = repo.get_publication(gen1)
    pub2 = repo.get_publication(gen2)

    assert pub1.status == "PUBLISHED"
    assert pub2.status == "QUARANTINED"

    # Reconstructed experiment must be retrievable and not a ghost
    published_exp = repo.get_published(exp1)
    assert published_exp is not None
    exp_rec, _ = published_exp
    assert exp_rec.experiment_id == exp1
    assert exp_rec.deterministic_payload == {"data": "recovered_payload"}
