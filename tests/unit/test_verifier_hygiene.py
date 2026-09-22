from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import pytest

from shiftguard.experiments.ids import stable_hash
import verification.verify_gate2_reproduction as vgr


@pytest.fixture(autouse=True)
def isolated_verification_output(tmp_path, monkeypatch) -> Path:
    output_dir = tmp_path / "test_verification" / "gate2"
    output_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("SHIFTGUARD_VERIFICATION_OUTPUT", str(output_dir))
    return output_dir


_last_dummy_hashes: dict[str, str] = {}
_last_dummy_data: dict[str, object] | None = None


def _generate_valid_gate2_data(unicode_tag: str = "") -> dict[str, object]:
    # 1. Conditions with matching preimage hashes
    conditions = {}
    for c in sorted(vgr.CONDITIONS):
        body = {
            "label": f"label_{c}_{unicode_tag}",
            "mask_id": "mask-123" if c.startswith("outage_") else None,
            "metrics": {
                "brier_score": 0.1,
                "log_loss": 0.2,
                "reliability": [{"count": 8238, "mean_probability": 0.5, "positive_fraction": 0.5}],
            },
        }
        preimage = {k: v for k, v in body.items() if k != "condition_id"}
        cid = stable_hash(preimage)[:24]
        conditions[c] = {"condition_id": cid, **body}

    # 2. Comparisons with matching preimage hashes and valid references
    no_outage_id = conditions["no_outage_raw"]["condition_id"]
    outage_id = conditions["outage_raw"]["condition_id"]
    comparisons = {}
    for i in range(6):
        comp_body = {
            "available": True,
            "deltas": {"brier_score": 0.0, "log_loss": 0.0},
            "earlier": no_outage_id,
            "later": outage_id,
            "lower_is_better": True,
            "name": f"comp_{i}",
            "reason": None,
        }
        preimage = {k: v for k, v in comp_body.items() if k != "comparison_id"}
        comp_id = stable_hash(preimage)[:24]
        comparisons[f"comp_{i}"] = {"comparison_id": comp_id, **comp_body}

    # 3. Artifact projections
    acq_payload = {
        "requested_labels": 50, "consumed_labels": 50, "distinct_labels": 50,
        "acquired_ids": [f"id_{i}" for i in range(50)],
        "order": [f"id_{i}" for i in range(50)],
        "provenance_note": f"provenance_tag_{unicode_tag}",
    }
    mask_payload = {
        "full_pool": {
            "record_ids": [f"pool_{i}" for i in range(4119)],
            "mask_id": "m1",
            "rates": {
                "observed_all_feature_cells_new_missing_rate": 0.1,
                "newly_missing_cells": 10,
                "observed_all_feature_cells": 100,
                "observed_history_group_new_missing_rate": 0.2,
                "observed_history_eligible_cells": 50,
                "total_missing_cells": 15,
                "natural_missing_cells": 5,
            },
            "description": f"full_pool_mask_{unicode_tag}",
        },
        "test": {
            "record_ids": [f"test_{i}" for i in range(8238)],
            "mask_id": "m2",
            "rates": {
                "observed_all_feature_cells_new_missing_rate": 0.1,
                "newly_missing_cells": 10,
                "observed_all_feature_cells": 100,
                "observed_history_group_new_missing_rate": 0.2,
                "observed_history_eligible_cells": 50,
                "total_missing_cells": 15,
                "natural_missing_cells": 5,
            },
            "description": f"test_mask_{unicode_tag}",
        },
        "acquired_subset": {
            "record_ids": [f"id_{i}" for i in range(50)],
            "parent_mask_id": "m1",
            "rates": {
                "observed_all_feature_cells_new_missing_rate": 0.1,
                "newly_missing_cells": 10,
                "observed_all_feature_cells": 100,
                "observed_history_group_new_missing_rate": 0.2,
                "observed_history_eligible_cells": 50,
                "total_missing_cells": 15,
                "natural_missing_cells": 5,
            },
            "description": f"subset_mask_{unicode_tag}",
        },
    }
    config_payload = {"protocol_id": "sg-protocol-1.0-draft"}
    seeds_payload = {"model": 123}
    metadata_payload = {"version": 1}

    # Deterministic DB payload
    db_payload = {
        "config": config_payload,
        "seeds": seeds_payload,
        "masks": mask_payload,
        "acquisition": acq_payload,
        "metadata": metadata_payload,
        "conditions": conditions,
        "comparisons": comparisons,
    }
    logical_content = stable_hash(db_payload)
    exp_id = logical_content[:24]

    return {
        "conditions": conditions,
        "comparisons": comparisons,
        "acquisition": acq_payload,
        "masks": mask_payload,
        "config": config_payload,
        "seeds": seeds_payload,
        "metadata": metadata_payload,
        "db_payload": db_payload,
        "logical_content": logical_content,
        "exp_id": exp_id,
    }


def _create_dummy_artifacts(art_dir: Path, unicode_tag: str = "") -> dict[str, str]:
    global _last_dummy_hashes, _last_dummy_data
    art_dir.mkdir(parents=True, exist_ok=True)
    data = _generate_valid_gate2_data(unicode_tag)
    _last_dummy_data = data

    (art_dir / "acquisition.json").write_text(json.dumps(data["acquisition"], ensure_ascii=False), encoding="utf-8")
    (art_dir / "masks.json").write_text(json.dumps(data["masks"], ensure_ascii=False), encoding="utf-8")
    (art_dir / "config.json").write_text(json.dumps(data["config"], ensure_ascii=False), encoding="utf-8")
    (art_dir / "seeds.json").write_text(json.dumps(data["seeds"], ensure_ascii=False), encoding="utf-8")
    (art_dir / "metadata.json").write_text(json.dumps(data["metadata"], ensure_ascii=False), encoding="utf-8")
    (art_dir / "conditions.json").write_text(json.dumps(data["conditions"], ensure_ascii=False), encoding="utf-8")
    (art_dir / "comparisons.json").write_text(json.dumps(data["comparisons"], ensure_ascii=False), encoding="utf-8")

    hashes = {
        key: hashlib.sha256((art_dir / f"{key}.json").read_bytes()).hexdigest()
        for key in ["acquisition", "masks", "config", "seeds", "metadata", "conditions", "comparisons"]
    }
    hashes["logical_content"] = data["logical_content"]
    _last_dummy_hashes = hashes
    return hashes


def _create_dummy_run_payload(exp_id: str, exec_id: str, unicode_tag: str = "", content_hashes: dict | None = None) -> dict:
    global _last_dummy_data
    if _last_dummy_data is None or unicode_tag != "":
        data = _generate_valid_gate2_data(unicode_tag)
    else:
        data = _last_dummy_data

    hashes = content_hashes if content_hashes is not None else dict(_last_dummy_hashes)
    return {
        "experiment_id": exp_id,
        "execution_id": exec_id,
        "conditions": data["conditions"],
        "comparisons": data["comparisons"],
        "content_hashes": hashes,
        "config": data["config"],
        "seeds": data["seeds"],
        "masks": data["masks"],
        "acquisition": data["acquisition"],
        "metadata": data["metadata"],
    }


def _seed_sqlite_experiment(db_path: str | Path, exp_id: str, exec_id: str, payload: dict, audit: dict) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS experiments (id TEXT PRIMARY KEY, payload_json TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS experiment_executions (execution_id TEXT PRIMARY KEY, experiment_id TEXT, audit_json TEXT)")
        conn.execute("INSERT OR IGNORE INTO experiments (id, payload_json) VALUES (?, ?)", (exp_id, json.dumps(payload, ensure_ascii=False)))
        conn.execute("INSERT OR REPLACE INTO experiment_executions (execution_id, experiment_id, audit_json) VALUES (?, ?, ?)", (exec_id, exp_id, json.dumps(audit, ensure_ascii=False)))
        conn.commit()
    finally:
        conn.close()


def test_stale_verification_json_archived_on_start(isolated_verification_output, monkeypatch) -> None:
    stale_file = isolated_verification_output / "verification.json"
    stale_content = '{"status": "stale_pass"}'
    stale_file.write_text(stale_content, encoding="utf-8")
    assert stale_file.exists()

    monkeypatch.delenv("SHIFTGUARD_TEST_POSTGRES_URL", raising=False)
    with pytest.raises(RuntimeError, match="SHIFTGUARD_TEST_POSTGRES_URL is required"):
        vgr.main()

    assert not stale_file.exists(), "Top-level stale verification.json must be cleared from top level"
    preserved = [p for p in isolated_verification_output.rglob("*.json") if p.read_text(encoding="utf-8") == stale_content]
    assert preserved, "Stale evidence was destroyed instead of archived"


@pytest.mark.parametrize("run_names", [
    ("sqlite-first", "sqlite-second", "postgres"),
    ("run-1", "run-2", "run-3"),
])
def test_failed_attempt_preserves_previous_run_files_and_prior_attempts(isolated_verification_output, monkeypatch, run_names) -> None:
    # 1. Pre-existing attempt directory
    attempts_dir = isolated_verification_output / "attempts"
    attempts_dir.mkdir(parents=True, exist_ok=True)
    prior_attempt_dir = attempts_dir / "attempt-20260901T000000Z-abcdef01"
    prior_attempt_dir.mkdir(parents=True, exist_ok=True)
    prior_verif = prior_attempt_dir / "verification.json"
    prior_verif_bytes = b'{"status": "prior_attempt_verified"}'
    prior_verif.write_bytes(prior_verif_bytes)

    # 2. Top-level legacy files
    top_verif_bytes = b'{"status": "top_level_legacy_pass"}'
    run1_bytes = b'{"run": 1, "data": "legacy"}'
    run2_bytes = b'{"run": 2, "data": "legacy"}'
    run3_bytes = b'{"run": 3, "data": "legacy"}'

    (isolated_verification_output / "verification.json").write_bytes(top_verif_bytes)
    for name, content in zip(run_names, (run1_bytes, run2_bytes, run3_bytes), strict=True):
        (isolated_verification_output / f"{name}.json").write_bytes(content)

    # 3. Trigger failure on missing postgres URL
    monkeypatch.delenv("SHIFTGUARD_TEST_POSTGRES_URL", raising=False)
    with pytest.raises(RuntimeError, match="SHIFTGUARD_TEST_POSTGRES_URL is required"):
        vgr.main()

    pointer = json.loads((isolated_verification_output / "current_attempt.json").read_text(encoding="utf-8"))
    assert pointer["status"] == "FAILED"

    # Prior attempt directory completely untouched
    assert prior_verif.read_bytes() == prior_verif_bytes

    # Legacy top-level files archived byte-for-byte
    for b in [top_verif_bytes, run1_bytes, run2_bytes, run3_bytes]:
        assert any(p.read_bytes() == b for p in isolated_verification_output.rglob("*.json"))

    # Top-level verification.json does not exist
    assert not (isolated_verification_output / "verification.json").exists()
    assert all(not (isolated_verification_output / f"{name}.json").exists() for name in run_names)


def test_archive_failure_cannot_leave_previous_pass_selected(isolated_verification_output, monkeypatch):
    previous_pointer = isolated_verification_output / "current_attempt.json"
    previous_pointer.write_text('{"status":"PASS","attempt_id":"old-attempt"}', encoding="utf-8")
    original_files = {"verification.json": b'{"old":"summary"}', "sqlite-first.json": b'{"old":"run"}'}
    for name, content in original_files.items():
        (isolated_verification_output / name).write_bytes(content)
    real_move = vgr.shutil.move
    calls = 0

    def fail_second_move(src, dst):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected archive failure")
        return real_move(src, dst)

    monkeypatch.setattr(vgr.shutil, "move", fail_second_move)
    with pytest.raises(OSError, match="injected archive failure"):
        vgr.main()
    pointer = json.loads(previous_pointer.read_text(encoding="utf-8"))
    assert pointer["status"] == "FAILED"
    assert pointer["attempt_id"] != "old-attempt"
    for content in original_files.values():
        assert any(path.read_bytes() == content for path in isolated_verification_output.rglob("*.json"))


def test_unrelated_database_and_sentinel_preserved(isolated_verification_output, tmp_path, monkeypatch) -> None:
    unrelated_db = tmp_path / "user_unrelated.db"
    unrelated_content = b"SQLITE_FORMAT_3_SIMULATED_USER_DATA_CONTENT_DO_NOT_DELETE"
    unrelated_db.write_bytes(unrelated_content)

    sentinel = tmp_path / "sentinel_summary.json"
    sentinel_content = '{"status": "external_historical_sentinel"}'
    sentinel.write_text(sentinel_content, encoding="utf-8")

    monkeypatch.delenv("SHIFTGUARD_TEST_POSTGRES_URL", raising=False)
    with pytest.raises(RuntimeError, match="SHIFTGUARD_TEST_POSTGRES_URL is required"):
        vgr.main()

    assert unrelated_db.read_bytes() == unrelated_content
    assert sentinel.read_text(encoding="utf-8") == sentinel_content


def test_shared_sqlite_reuse_within_invocation(isolated_verification_output, tmp_path, monkeypatch) -> None:
    captured_urls: list[str] = []
    real_subprocess_run = vgr.subprocess.run

    valid = _generate_valid_gate2_data()
    exp_id = valid["exp_id"]
    fake_app = tmp_path / "fake_app"
    _create_dummy_artifacts(fake_app / "var" / "artifacts" / exp_id)
    monkeypatch.setattr(vgr, "APP", fake_app)

    call_count = 0

    def fake_subprocess_run(cmd, *args, **kwargs):
        nonlocal call_count
        if cmd[0] == "git":
            return real_subprocess_run(cmd, *args, **kwargs)
        if "--db-url" in cmd:
            idx = cmd.index("--db-url")
            captured_urls.append(cmd[idx + 1])
        call_count += 1
        if call_count <= 2:
            payload = _create_dummy_run_payload(exp_id, f"exec-sqlite-{call_count}")
            class FakeSuccess:
                returncode = 0
                stdout = json.dumps(payload)
                stderr = ""
            return FakeSuccess()
        class FakeHalt:
            returncode = 1
            stderr = "halt_after_both_sqlite_runs"
        return FakeHalt()

    monkeypatch.setenv("SHIFTGUARD_TEST_POSTGRES_URL", "postgresql://user:pass@localhost:5432/test")
    monkeypatch.setenv("SHIFTGUARD_EXPECTED_COMMIT", "test_commit")
    monkeypatch.setattr(vgr.subprocess, "run", fake_subprocess_run)

    with pytest.raises(RuntimeError, match="postgres failed: halt_after_both_sqlite_runs"):
        vgr.main()

    assert len(captured_urls) == 3
    assert captured_urls[0] == captured_urls[1]
    assert captured_urls[0].startswith("sqlite:///")
    assert "reproduction.db" in captured_urls[0]
    assert captured_urls[2].startswith("postgresql://")


def test_invocation_isolation(isolated_verification_output, monkeypatch) -> None:
    captured_urls: list[str] = []
    real_subprocess_run = vgr.subprocess.run

    def fake_subprocess_run(cmd, *args, **kwargs):
        if cmd[0] == "git":
            return real_subprocess_run(cmd, *args, **kwargs)
        if "--db-url" in cmd:
            idx = cmd.index("--db-url")
            captured_urls.append(cmd[idx + 1])
        class FakeRes:
            returncode = 1
            stderr = "halt"
        return FakeRes()

    monkeypatch.setenv("SHIFTGUARD_TEST_POSTGRES_URL", "postgresql://user:pass@localhost:5432/test")
    monkeypatch.setenv("SHIFTGUARD_EXPECTED_COMMIT", "test_commit")
    monkeypatch.setattr(vgr.subprocess, "run", fake_subprocess_run)

    with pytest.raises(RuntimeError, match="sqlite-first failed"):
        vgr.main()
    with pytest.raises(RuntimeError, match="sqlite-first failed"):
        vgr.main()

    assert len(captured_urls) == 2
    assert captured_urls[0] != captured_urls[1]


def test_utf8_reading_path_and_publication(isolated_verification_output, tmp_path, monkeypatch) -> None:
    unicode_tag = "üñîçødë_tëst_µ_日本語_🚀"
    valid = _generate_valid_gate2_data(unicode_tag)
    exp_id = valid["exp_id"]
    fake_app = tmp_path / "fake_app"
    _create_dummy_artifacts(fake_app / "var" / "artifacts" / exp_id, unicode_tag=unicode_tag)
    monkeypatch.setattr(vgr, "APP", fake_app)

    real_subprocess_run = vgr.subprocess.run
    call_count = 0

    def fake_subprocess_run(cmd, *args, **kwargs):
        nonlocal call_count
        if cmd[0] == "git":
            return real_subprocess_run(cmd, *args, **kwargs)
        call_count += 1
        payload = _create_dummy_run_payload(exp_id, f"exec-{call_count}", unicode_tag=unicode_tag)
        if "--db-url" in cmd:
            url = cmd[cmd.index("--db-url") + 1]
            if url.startswith("sqlite:///"):
                db_file = url[len("sqlite:///"):]
                audit = {"provenance": {"git": {"available": True, "dirty": False, "head": "test_commit"}}}
                _seed_sqlite_experiment(db_file, exp_id, f"exec-{call_count}", payload, audit)
        class FakeSuccess:
            returncode = 0
            stdout = json.dumps(payload, ensure_ascii=False)
            stderr = ""
        return FakeSuccess()

    class FakePostgresConn:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def execute(self, query, params):
            class FakeCursor:
                def fetchone(self):
                    p = _create_dummy_run_payload(exp_id, "exec-1", unicode_tag=unicode_tag)
                    return (json.dumps(p, ensure_ascii=False),)
                def fetchall(self):
                    audit = {"provenance": {"git": {"available": True, "dirty": False, "head": "test_commit"}}}
                    return [("exec-3", json.dumps(audit, ensure_ascii=False))]
            return FakeCursor()

    monkeypatch.setenv("SHIFTGUARD_TEST_POSTGRES_URL", "postgresql://user:pass@localhost:5432/test")
    monkeypatch.setenv("SHIFTGUARD_EXPECTED_COMMIT", "test_commit")
    monkeypatch.setattr(vgr.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(vgr.psycopg, "connect", lambda url: FakePostgresConn())

    vgr.main()

    verif_path = isolated_verification_output / "verification.json"
    assert verif_path.exists()
    content = verif_path.read_text(encoding="utf-8")
    assert unicode_tag in content
    data = json.loads(content)
    assert data["status"] == "passed"
    assert data["verified_provenance"]["git_available"] is True
    assert data["verified_provenance"]["git_dirty"] is False
    assert data["verified_provenance"]["verified_commit"] == "test_commit"


def test_successful_publication_flow(isolated_verification_output, tmp_path, monkeypatch) -> None:
    previous_files = {
        name: json.dumps({"historical_file": name}).encode("utf-8")
        for name in ("verification.json", "sqlite-first.json", "sqlite-second.json", "postgres.json")
    }
    for name, content in previous_files.items():
        (isolated_verification_output / name).write_bytes(content)
    prior_attempt = isolated_verification_output / "attempts" / "prior-attempt"
    prior_attempt.mkdir(parents=True)
    prior_file = prior_attempt / "verification.json"
    prior_bytes = b'{"prior_attempt":"preserve-byte-for-byte"}'
    prior_file.write_bytes(prior_bytes)
    valid = _generate_valid_gate2_data()
    exp_id = valid["exp_id"]
    fake_app = tmp_path / "fake_app"
    _create_dummy_artifacts(fake_app / "var" / "artifacts" / exp_id)
    monkeypatch.setattr(vgr, "APP", fake_app)

    real_subprocess_run = vgr.subprocess.run
    call_count = 0

    def fake_subprocess_run(cmd, *args, **kwargs):
        nonlocal call_count
        if cmd[0] == "git":
            return real_subprocess_run(cmd, *args, **kwargs)
        call_count += 1
        payload = _create_dummy_run_payload(exp_id, f"exec-{call_count}")
        if "--db-url" in cmd:
            url = cmd[cmd.index("--db-url") + 1]
            if url.startswith("sqlite:///"):
                db_file = url[len("sqlite:///"):]
                audit = {"provenance": {"git": {"available": True, "dirty": False, "head": "test_commit"}}}
                _seed_sqlite_experiment(db_file, exp_id, f"exec-{call_count}", payload, audit)
        class FakeSuccess:
            returncode = 0
            stdout = json.dumps(payload)
            stderr = ""
        return FakeSuccess()

    class FakePostgresConn:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def execute(self, query, params):
            class FakeCursor:
                def fetchone(self):
                    p = _create_dummy_run_payload(exp_id, "exec-1")
                    return (json.dumps(p),)
                def fetchall(self):
                    audit = {"provenance": {"git": {"available": True, "dirty": False, "head": "test_commit"}}}
                    return [("exec-3", json.dumps(audit))]
            return FakeCursor()

    monkeypatch.setenv("SHIFTGUARD_TEST_POSTGRES_URL", "postgresql://user:pass@localhost:5432/test")
    monkeypatch.setenv("SHIFTGUARD_EXPECTED_COMMIT", "test_commit")
    monkeypatch.setattr(vgr.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(vgr.psycopg, "connect", lambda url: FakePostgresConn())

    vgr.main()

    assert prior_file.read_bytes() == prior_bytes
    for name, content in previous_files.items():
        assert any(path.read_bytes() == content for path in (isolated_verification_output / "attempts").rglob(name)), name
        assert (isolated_verification_output / name).read_bytes() != content
    for name in ("verification.json", "sqlite-first.json", "sqlite-second.json", "postgres.json"):
        published_file = isolated_verification_output / name
        assert published_file.exists(), f"Expected {name} to be published"
        parsed = json.loads(published_file.read_text(encoding="utf-8"))
        assert parsed is not None

    summary = json.loads((isolated_verification_output / "verification.json").read_text(encoding="utf-8"))
    assert summary["status"] == "passed"
    assert summary["sqlite_and_postgres_payloads_equal"] is True
    assert summary["verified_provenance"]["git_available"] is True
    assert summary["verified_provenance"]["git_dirty"] is False
    assert summary["verified_provenance"]["verified_commit"] == "test_commit"
    assert "verifier_sha256" in summary["verified_provenance"]

    # Verify attempt isolation
    pointer = isolated_verification_output / "current_attempt.json"
    assert pointer.is_file(), "current_attempt.json must exist"
    pointer_data = json.loads(pointer.read_text(encoding="utf-8"))
    assert pointer_data["status"] == "PASS"
    attempt_dir = isolated_verification_output / "attempts" / pointer_data["attempt_id"]
    assert attempt_dir.is_dir()
    assert (attempt_dir / "verification.json").is_file()


def test_late_failure_prevents_publication(isolated_verification_output, tmp_path, monkeypatch) -> None:
    call_count = 0
    real_subprocess_run = vgr.subprocess.run

    valid = _generate_valid_gate2_data()
    exp_id = valid["exp_id"]
    fake_app = tmp_path / "fake_app"
    _create_dummy_artifacts(fake_app / "var" / "artifacts" / exp_id)
    monkeypatch.setattr(vgr, "APP", fake_app)

    def fake_subprocess_run(cmd, *args, **kwargs):
        nonlocal call_count
        if cmd[0] == "git":
            return real_subprocess_run(cmd, *args, **kwargs)
        call_count += 1
        if call_count <= 2:
            dummy = _create_dummy_run_payload(exp_id, f"exec-{call_count}")
            class FakeSuccess:
                returncode = 0
                stdout = json.dumps(dummy)
                stderr = ""
            return FakeSuccess()
        class FakeFail:
            returncode = 1
            stderr = "postgres_network_error"
        return FakeFail()

    monkeypatch.setenv("SHIFTGUARD_TEST_POSTGRES_URL", "postgresql://user:pass@localhost:5432/test")
    monkeypatch.setenv("SHIFTGUARD_EXPECTED_COMMIT", "test_commit")
    monkeypatch.setattr(vgr.subprocess, "run", fake_subprocess_run)

    with pytest.raises(RuntimeError, match="postgres failed: postgres_network_error"):
        vgr.main()

    assert not (isolated_verification_output / "verification.json").exists()
    assert not (isolated_verification_output / "sqlite-first.json").exists()
    assert not (isolated_verification_output / "sqlite-second.json").exists()


def test_provenance_validation_clean_succeeds() -> None:
    execution_ids = ["e1", "e2", "e3"]
    audits = {
        "e1": {"provenance": {"git": {"available": True, "dirty": False, "head": "commit123"}}},
        "e2": {"provenance": {"git": {"available": True, "dirty": False, "head": "commit123"}}},
        "e3": {"provenance": {"git": {"available": True, "dirty": False, "head": "commit123"}}},
    }
    result = vgr.validate_execution_provenance(execution_ids, audits, "commit123")
    assert result["git_available"] is True
    assert result["git_dirty"] is False
    assert result["verified_commit"] == "commit123"


def test_provenance_validation_rejects_missing_dirty() -> None:
    audits = {
        "e1": {"provenance": {"git": {"available": True, "head": "commit123"}}},
    }
    with pytest.raises(AssertionError, match="Git provenance dirty must be False"):
        vgr.validate_execution_provenance(["e1"], audits, "commit123")


def test_provenance_validation_rejects_none_dirty() -> None:
    audits = {
        "e1": {"provenance": {"git": {"available": True, "dirty": None, "head": "commit123"}}},
    }
    with pytest.raises(AssertionError, match="Git provenance dirty must be False"):
        vgr.validate_execution_provenance(["e1"], audits, "commit123")


def test_provenance_validation_rejects_non_boolean_dirty() -> None:
    for invalid_dirty in ("false", "dirty", 0, 1, [], {}):
        audits = {
            "e1": {"provenance": {"git": {"available": True, "dirty": invalid_dirty, "head": "commit123"}}},
        }
        with pytest.raises(AssertionError, match="Git provenance dirty must be False"):
            vgr.validate_execution_provenance(["e1"], audits, "commit123")


def test_provenance_validation_rejects_dirty_boolean() -> None:
    audits = {
        "e1": {"provenance": {"git": {"available": True, "dirty": True, "head": "commit123"}}},
    }
    with pytest.raises(AssertionError, match="Git provenance dirty must be False"):
        vgr.validate_execution_provenance(["e1"], audits, "commit123")


def test_provenance_validation_rejects_missing_available() -> None:
    audits = {
        "e1": {"provenance": {"git": {"dirty": False, "head": "commit123"}}},
    }
    with pytest.raises(AssertionError, match="Git provenance available must be True"):
        vgr.validate_execution_provenance(["e1"], audits, "commit123")


def test_provenance_validation_rejects_none_available() -> None:
    audits = {
        "e1": {"provenance": {"git": {"available": None, "dirty": False, "head": "commit123"}}},
    }
    with pytest.raises(AssertionError, match="Git provenance available must be True"):
        vgr.validate_execution_provenance(["e1"], audits, "commit123")


def test_provenance_validation_rejects_non_boolean_available() -> None:
    for invalid_available in ("true", "yes", 1, 0, [], {}):
        audits = {
            "e1": {"provenance": {"git": {"available": invalid_available, "dirty": False, "head": "commit123"}}},
        }
        with pytest.raises(AssertionError, match="Git provenance available must be True"):
            vgr.validate_execution_provenance(["e1"], audits, "commit123")


def test_provenance_validation_rejects_unavailable_boolean() -> None:
    audits = {
        "e1": {"provenance": {"git": {"available": False, "dirty": False, "head": "commit123"}}},
    }
    with pytest.raises(AssertionError, match="Git provenance available must be True"):
        vgr.validate_execution_provenance(["e1"], audits, "commit123")


def test_provenance_validation_rejects_wrong_head() -> None:
    audits = {
        "e1": {"provenance": {"git": {"available": True, "dirty": False, "head": "wrong_commit"}}},
    }
    with pytest.raises(AssertionError, match="HEAD wrong_commit != expected commit expected_commit"):
        vgr.validate_execution_provenance(["e1"], audits, "expected_commit")


def test_provenance_validation_rejects_missing_audit() -> None:
    audits = {
        "e1": {"provenance": {"git": {"available": True, "dirty": False, "head": "commit123"}}},
    }
    with pytest.raises(AssertionError, match="Audit missing for execution e2"):
        vgr.validate_execution_provenance(["e1", "e2"], audits, "commit123")


def test_provenance_rejection_prevents_publication(isolated_verification_output, tmp_path, monkeypatch) -> None:
    valid = _generate_valid_gate2_data()
    exp_id = valid["exp_id"]
    fake_app = tmp_path / "fake_app"
    _create_dummy_artifacts(fake_app / "var" / "artifacts" / exp_id)
    monkeypatch.setattr(vgr, "APP", fake_app)

    real_subprocess_run = vgr.subprocess.run
    call_count = 0

    def fake_subprocess_run(cmd, *args, **kwargs):
        nonlocal call_count
        if cmd[0] == "git":
            return real_subprocess_run(cmd, *args, **kwargs)
        call_count += 1
        payload = _create_dummy_run_payload(exp_id, f"exec-{call_count}")
        if "--db-url" in cmd:
            url = cmd[cmd.index("--db-url") + 1]
            if url.startswith("sqlite:///"):
                db_file = url[len("sqlite:///"):]
                invalid_audit = {"provenance": {"git": {"available": True, "dirty": None, "head": "test_commit"}}}
                _seed_sqlite_experiment(db_file, exp_id, f"exec-{call_count}", payload, invalid_audit)
        class FakeSuccess:
            returncode = 0
            stdout = json.dumps(payload)
            stderr = ""
        return FakeSuccess()

    class FakePostgresConn:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def execute(self, query, params):
            class FakeCursor:
                def fetchone(self):
                    p = _create_dummy_run_payload(exp_id, "exec-1")
                    return (json.dumps(p),)
                def fetchall(self):
                    invalid_audit = {"provenance": {"git": {"available": True, "dirty": None, "head": "test_commit"}}}
                    return [("exec-3", json.dumps(invalid_audit))]
            return FakeCursor()

    monkeypatch.setenv("SHIFTGUARD_TEST_POSTGRES_URL", "postgresql://user:pass@localhost:5432/test")
    monkeypatch.setenv("SHIFTGUARD_EXPECTED_COMMIT", "test_commit")
    monkeypatch.setattr(vgr.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(vgr.psycopg, "connect", lambda url: FakePostgresConn())

    with pytest.raises(AssertionError, match="Git provenance dirty must be False"):
        vgr.main()

    assert not (isolated_verification_output / "verification.json").exists()
    assert not (isolated_verification_output / "sqlite-first.json").exists()
    assert not (isolated_verification_output / "sqlite-second.json").exists()
    assert not (isolated_verification_output / "postgres.json").exists()


def test_verifier_rejects_empty_content_hashes(isolated_verification_output, tmp_path, monkeypatch) -> None:
    valid = _generate_valid_gate2_data()
    exp_id = valid["exp_id"]
    fake_app = tmp_path / "fake_app"
    _create_dummy_artifacts(fake_app / "var" / "artifacts" / exp_id)
    monkeypatch.setattr(vgr, "APP", fake_app)

    def fake_subprocess_run(cmd, *args, **kwargs):
        payload = _create_dummy_run_payload(exp_id, "exec-1", content_hashes={})
        class FakeSuccess:
            returncode = 0
            stdout = json.dumps(payload)
            stderr = ""
        return FakeSuccess()

    monkeypatch.setenv("SHIFTGUARD_TEST_POSTGRES_URL", "postgresql://user:pass@localhost:5432/test")
    monkeypatch.setenv("SHIFTGUARD_EXPECTED_COMMIT", "test_commit")
    monkeypatch.setattr(vgr.subprocess, "run", fake_subprocess_run)

    with pytest.raises(AssertionError, match="content_hashes missing required Gate 2 artifact keys"):
        vgr.main()

    assert not (isolated_verification_output / "verification.json").exists()


def test_verifier_rejects_extra_content_hashes_key(isolated_verification_output, tmp_path, monkeypatch) -> None:
    valid = _generate_valid_gate2_data()
    exp_id = valid["exp_id"]
    fake_app = tmp_path / "fake_app"
    hashes = _create_dummy_artifacts(fake_app / "var" / "artifacts" / exp_id)
    hashes["unexpected_extra_key"] = "0" * 64
    monkeypatch.setattr(vgr, "APP", fake_app)

    def fake_subprocess_run(cmd, *args, **kwargs):
        payload = _create_dummy_run_payload(exp_id, "exec-1", content_hashes=hashes)
        class FakeSuccess:
            returncode = 0
            stdout = json.dumps(payload)
            stderr = ""
        return FakeSuccess()

    monkeypatch.setenv("SHIFTGUARD_TEST_POSTGRES_URL", "postgresql://user:pass@localhost:5432/test")
    monkeypatch.setenv("SHIFTGUARD_EXPECTED_COMMIT", "test_commit")
    monkeypatch.setattr(vgr.subprocess, "run", fake_subprocess_run)

    with pytest.raises(AssertionError, match="content_hashes missing required Gate 2 artifact keys"):
        vgr.main()

    assert not (isolated_verification_output / "verification.json").exists()


def test_verifier_rejects_corrupted_artifact_hash(isolated_verification_output, tmp_path, monkeypatch) -> None:
    valid = _generate_valid_gate2_data()
    exp_id = valid["exp_id"]
    fake_app = tmp_path / "fake_app"
    _create_dummy_artifacts(fake_app / "var" / "artifacts" / exp_id)
    # Corrupt masks.json on disk
    (fake_app / "var" / "artifacts" / exp_id / "masks.json").write_bytes(b'{"corrupt": true}')
    monkeypatch.setattr(vgr, "APP", fake_app)

    def fake_subprocess_run(cmd, *args, **kwargs):
        payload = _create_dummy_run_payload(exp_id, "exec-1")
        class FakeSuccess:
            returncode = 0
            stdout = json.dumps(payload)
            stderr = ""
        return FakeSuccess()

    monkeypatch.setenv("SHIFTGUARD_TEST_POSTGRES_URL", "postgresql://user:pass@localhost:5432/test")
    monkeypatch.setenv("SHIFTGUARD_EXPECTED_COMMIT", "test_commit")
    monkeypatch.setattr(vgr.subprocess, "run", fake_subprocess_run)

    with pytest.raises(AssertionError, match="Artifact hash mismatch for masks"):
        vgr.main()

    assert not (isolated_verification_output / "verification.json").exists()


def test_verifier_rejects_corrupted_condition_preimage(isolated_verification_output, tmp_path, monkeypatch) -> None:
    valid = _generate_valid_gate2_data()
    exp_id = valid["exp_id"]
    fake_app = tmp_path / "fake_app"
    _create_dummy_artifacts(fake_app / "var" / "artifacts" / exp_id)
    monkeypatch.setattr(vgr, "APP", fake_app)

    def fake_subprocess_run(cmd, *args, **kwargs):
        payload = _create_dummy_run_payload(exp_id, "exec-1")
        # Tamper with condition metrics without updating condition_id
        payload["conditions"]["no_outage_raw"]["metrics"]["brier_score"] = 0.999
        class FakeSuccess:
            returncode = 0
            stdout = json.dumps(payload)
            stderr = ""
        return FakeSuccess()

    monkeypatch.setenv("SHIFTGUARD_TEST_POSTGRES_URL", "postgresql://user:pass@localhost:5432/test")
    monkeypatch.setenv("SHIFTGUARD_EXPECTED_COMMIT", "test_commit")
    monkeypatch.setattr(vgr.subprocess, "run", fake_subprocess_run)

    with pytest.raises(AssertionError, match="Condition no_outage_raw ID mismatch"):
        vgr.main()


def test_verifier_rejects_corrupted_comparison_preimage(isolated_verification_output, tmp_path, monkeypatch) -> None:
    valid = _generate_valid_gate2_data()
    exp_id = valid["exp_id"]
    fake_app = tmp_path / "fake_app"
    _create_dummy_artifacts(fake_app / "var" / "artifacts" / exp_id)
    monkeypatch.setattr(vgr, "APP", fake_app)

    def fake_subprocess_run(cmd, *args, **kwargs):
        payload = _create_dummy_run_payload(exp_id, "exec-1")
        # Tamper with comparison deltas without updating comparison_id
        payload["comparisons"]["comp_0"]["deltas"]["brier_score"] = 0.999
        class FakeSuccess:
            returncode = 0
            stdout = json.dumps(payload)
            stderr = ""
        return FakeSuccess()

    monkeypatch.setenv("SHIFTGUARD_TEST_POSTGRES_URL", "postgresql://user:pass@localhost:5432/test")
    monkeypatch.setenv("SHIFTGUARD_EXPECTED_COMMIT", "test_commit")
    monkeypatch.setattr(vgr.subprocess, "run", fake_subprocess_run)

    with pytest.raises(AssertionError, match="Comparison comp_0 ID mismatch"):
        vgr.main()


def test_verifier_rejects_database_projection_mismatch(isolated_verification_output, tmp_path, monkeypatch) -> None:
    valid = _generate_valid_gate2_data()
    exp_id = valid["exp_id"]
    fake_app = tmp_path / "fake_app"
    _create_dummy_artifacts(fake_app / "var" / "artifacts" / exp_id)
    # Alter config.json on disk and update content_hashes so hash check passes but projection check fails
    new_config = {"protocol_id": "altered-protocol-for-projection-failure"}
    config_bytes = json.dumps(new_config).encode("utf-8")
    (fake_app / "var" / "artifacts" / exp_id / "config.json").write_bytes(config_bytes)
    monkeypatch.setattr(vgr, "APP", fake_app)

    real_subprocess_run = vgr.subprocess.run
    call_count = 0

    def fake_subprocess_run(cmd, *args, **kwargs):
        nonlocal call_count
        if cmd[0] == "git":
            return real_subprocess_run(cmd, *args, **kwargs)
        call_count += 1
        payload = _create_dummy_run_payload(exp_id, f"exec-{call_count}")
        payload["content_hashes"]["config"] = hashlib.sha256(config_bytes).hexdigest()
        if "--db-url" in cmd:
            url = cmd[cmd.index("--db-url") + 1]
            if url.startswith("sqlite:///"):
                db_file = url[len("sqlite:///"):]
                audit = {"provenance": {"git": {"available": True, "dirty": False, "head": "test_commit"}}}
                _seed_sqlite_experiment(db_file, exp_id, f"exec-{call_count}", payload, audit)
        class FakeSuccess:
            returncode = 0
            stdout = json.dumps(payload)
            stderr = ""
        return FakeSuccess()

    class FakePostgresConn:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def execute(self, query, params):
            class FakeCursor:
                def fetchone(self):
                    p = _create_dummy_run_payload(exp_id, "exec-1")
                    p["content_hashes"]["config"] = hashlib.sha256(config_bytes).hexdigest()
                    return (json.dumps(p),)
                def fetchall(self):
                    audit = {"provenance": {"git": {"available": True, "dirty": False, "head": "test_commit"}}}
                    return [("exec-3", json.dumps(audit))]
            return FakeCursor()

    monkeypatch.setenv("SHIFTGUARD_TEST_POSTGRES_URL", "postgresql://user:pass@localhost:5432/test")
    monkeypatch.setenv("SHIFTGUARD_EXPECTED_COMMIT", "test_commit")
    monkeypatch.setattr(vgr.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(vgr.psycopg, "connect", lambda url: FakePostgresConn())

    with pytest.raises(AssertionError, match="Database projection config does not match saved artifact"):
        vgr.main()


def test_verifier_rejects_logical_content_digest_mismatch(isolated_verification_output, tmp_path, monkeypatch) -> None:
    valid = _generate_valid_gate2_data()
    exp_id = valid["exp_id"]
    fake_app = tmp_path / "fake_app"
    _create_dummy_artifacts(fake_app / "var" / "artifacts" / exp_id)
    monkeypatch.setattr(vgr, "APP", fake_app)

    real_subprocess_run = vgr.subprocess.run
    call_count = 0

    def fake_subprocess_run(cmd, *args, **kwargs):
        nonlocal call_count
        if cmd[0] == "git":
            return real_subprocess_run(cmd, *args, **kwargs)
        call_count += 1
        payload = _create_dummy_run_payload(exp_id, f"exec-{call_count}")
        # Tamper with logical_content hash
        payload["content_hashes"]["logical_content"] = "0" * 64
        if "--db-url" in cmd:
            url = cmd[cmd.index("--db-url") + 1]
            if url.startswith("sqlite:///"):
                db_file = url[len("sqlite:///"):]
                audit = {"provenance": {"git": {"available": True, "dirty": False, "head": "test_commit"}}}
                _seed_sqlite_experiment(db_file, exp_id, f"exec-{call_count}", payload, audit)
        class FakeSuccess:
            returncode = 0
            stdout = json.dumps(payload)
            stderr = ""
        return FakeSuccess()

    class FakePostgresConn:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def execute(self, query, params):
            class FakeCursor:
                def fetchone(self):
                    p = _create_dummy_run_payload(exp_id, "exec-1")
                    p["content_hashes"]["logical_content"] = "0" * 64
                    return (json.dumps(p),)
                def fetchall(self):
                    audit = {"provenance": {"git": {"available": True, "dirty": False, "head": "test_commit"}}}
                    return [("exec-3", json.dumps(audit))]
            return FakeCursor()

    monkeypatch.setenv("SHIFTGUARD_TEST_POSTGRES_URL", "postgresql://user:pass@localhost:5432/test")
    monkeypatch.setenv("SHIFTGUARD_EXPECTED_COMMIT", "test_commit")
    monkeypatch.setattr(vgr.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(vgr.psycopg, "connect", lambda url: FakePostgresConn())

    with pytest.raises(AssertionError, match="Logical content digest mismatch"):
        vgr.main()


def test_gate2_current_attempt_pointer_records_failed_status_and_attempt_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("SHIFTGUARD_TEST_POSTGRES_URL", raising=False)
    monkeypatch.setenv("SHIFTGUARD_VERIFICATION_OUTPUT", str(tmp_path))

    with pytest.raises(RuntimeError, match="SHIFTGUARD_TEST_POSTGRES_URL is required"):
        vgr.main()

    pointer = tmp_path / "current_attempt.json"
    assert pointer.is_file(), "current_attempt.json must exist"
    pointer_data = json.loads(pointer.read_text(encoding="utf-8"))
    assert pointer_data["status"] == "FAILED"
    assert "SHIFTGUARD_TEST_POSTGRES_URL is required" in pointer_data["error"]
    assert "attempt_id" in pointer_data
    assert "failed_at" in pointer_data

    attempt_dir = tmp_path / "attempts" / pointer_data["attempt_id"]
    assert attempt_dir.is_dir(), f"Attempt directory {attempt_dir} must have been created"
