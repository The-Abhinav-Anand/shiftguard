from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import pytest

import verification.verify_gate2_reproduction as vgr


@pytest.fixture(autouse=True)
def isolated_verification_output(tmp_path, monkeypatch) -> Path:
    output_dir = tmp_path / "test_verification" / "gate2"
    output_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("SHIFTGUARD_VERIFICATION_OUTPUT", str(output_dir))
    return output_dir


def _create_dummy_artifacts(art_dir: Path, unicode_tag: str = "") -> None:
    art_dir.mkdir(parents=True, exist_ok=True)
    acq_payload = {
        "requested_labels": 50, "consumed_labels": 50, "distinct_labels": 50,
        "acquired_ids": [f"id_{i}" for i in range(50)],
        "order": [f"id_{i}" for i in range(50)],
        "provenance_note": f"provenance_tag_{unicode_tag}",
    }
    (art_dir / "acquisition.json").write_text(json.dumps(acq_payload, ensure_ascii=False), encoding="utf-8")
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
    (art_dir / "masks.json").write_text(json.dumps(mask_payload, ensure_ascii=False), encoding="utf-8")


def _create_dummy_run_payload(exp_id: str, exec_id: str, unicode_tag: str = "") -> dict:
    dummy_conditions = {
        c: {
            "condition_id": f"cid-{c}",
            "mask_id": "mask-123" if c.startswith("outage_") else None,
            "metrics": {
                "brier_score": 0.1,
                "log_loss": 0.2,
                "reliability": [{"count": 8238, "mean_probability": 0.5, "positive_fraction": 0.5}],
            },
            "label": f"label_{c}_{unicode_tag}",
        }
        for c in vgr.CONDITIONS
    }
    dummy_comparisons = {
        f"comp_{i}": {
            "earlier": "cid-no_outage_raw",
            "later": "cid-outage_raw",
            "deltas": {"brier_score": 0.0, "log_loss": 0.0},
        }
        for i in range(6)
    }
    return {
        "experiment_id": exp_id,
        "execution_id": exec_id,
        "conditions": dummy_conditions,
        "comparisons": dummy_comparisons,
        "content_hashes": {},
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


def test_stale_verification_json_unlinked_on_start(isolated_verification_output, monkeypatch) -> None:
    stale_file = isolated_verification_output / "verification.json"
    stale_file.write_text('{"status": "stale_pass"}', encoding="utf-8")
    assert stale_file.exists()

    monkeypatch.delenv("SHIFTGUARD_TEST_POSTGRES_URL", raising=False)
    with pytest.raises(RuntimeError, match="SHIFTGUARD_TEST_POSTGRES_URL is required"):
        vgr.main()

    assert not stale_file.exists()


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

    exp_id = "exp_sqlite_reuse"
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
            # Let both sqlite-first and sqlite-second succeed
            payload = _create_dummy_run_payload(exp_id, f"exec-sqlite-{call_count}")
            class FakeSuccess:
                returncode = 0
                stdout = json.dumps(payload)
                stderr = ""
            return FakeSuccess()
        # Halt before executing postgres
        class FakeHalt:
            returncode = 1
            stderr = "halt_after_both_sqlite_runs"
        return FakeHalt()

    monkeypatch.setenv("SHIFTGUARD_TEST_POSTGRES_URL", "postgresql://user:pass@localhost:5432/test")
    monkeypatch.setenv("SHIFTGUARD_EXPECTED_COMMIT", "test_commit")
    monkeypatch.setattr(vgr.subprocess, "run", fake_subprocess_run)

    with pytest.raises(RuntimeError, match="postgres failed: halt_after_both_sqlite_runs"):
        vgr.main()

    # Must capture at least both SQLite executions
    assert len(captured_urls) == 3
    # sqlite-first (index 0) and sqlite-second (index 1) MUST share the exact same database URL
    assert captured_urls[0] == captured_urls[1]
    assert captured_urls[0].startswith("sqlite:///")
    assert "reproduction.db" in captured_urls[0]
    # postgres (index 2) must differ
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
    # Two distinct invocations must use two distinct temporary directories / database paths
    assert captured_urls[0] != captured_urls[1]


def test_utf8_reading_path_and_publication(isolated_verification_output, tmp_path, monkeypatch) -> None:
    exp_id = "exp_utf8_verify"
    unicode_tag = "üñîçødë_tëst_µ_日本語_🚀"
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
    exp_id = "exp_successful_publication"
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


def test_late_failure_prevents_publication(isolated_verification_output, tmp_path, monkeypatch) -> None:
    call_count = 0
    real_subprocess_run = vgr.subprocess.run

    exp_id = "exp_late_failure"
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
    exp_id = "exp_provenance_rejection"
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
                # Inject dirty=None (invalid boolean provenance)
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

    # Crucial assertion: rejection MUST prevent publication of PASS or output files
    assert not (isolated_verification_output / "verification.json").exists()
    assert not (isolated_verification_output / "sqlite-first.json").exists()
    assert not (isolated_verification_output / "sqlite-second.json").exists()
    assert not (isolated_verification_output / "postgres.json").exists()
