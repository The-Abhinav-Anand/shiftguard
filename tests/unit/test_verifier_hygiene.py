from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import pytest

import verification.verify_gate2_reproduction as vgr


@pytest.fixture(autouse=True)
def isolated_verification_output(tmp_path, monkeypatch) -> Path:
    output_dir = tmp_path / "test_verification" / "gate2"
    output_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("SHIFTGUARD_VERIFICATION_OUTPUT", str(output_dir))
    return output_dir


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


def test_shared_sqlite_reuse_within_invocation(isolated_verification_output, monkeypatch) -> None:
    captured_urls = []
    real_subprocess_run = vgr.subprocess.run

    def fake_subprocess_run(cmd, *args, **kwargs):
        if cmd[0] == "git":
            return real_subprocess_run(cmd, *args, **kwargs)
        if "--db-url" in cmd:
            idx = cmd.index("--db-url")
            captured_urls.append(cmd[idx + 1])
        class FakeRes:
            returncode = 1
            stderr = "stop_after_capturing"
        return FakeRes()

    monkeypatch.setenv("SHIFTGUARD_TEST_POSTGRES_URL", "postgresql://user:pass@localhost:5432/test")
    monkeypatch.setenv("SHIFTGUARD_EXPECTED_COMMIT", "test_commit")
    monkeypatch.setattr(vgr.subprocess, "run", fake_subprocess_run)

    with pytest.raises(RuntimeError, match="sqlite-first failed: stop_after_capturing"):
        vgr.main()

    assert len(captured_urls) == 1
    first_url = captured_urls[0]
    assert first_url.startswith("sqlite:///")
    assert "reproduction.db" in first_url


def test_invocation_isolation(isolated_verification_output, monkeypatch) -> None:
    captured_urls = []
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


def test_utf8_json_read_preserves_characters(tmp_path) -> None:
    data = {"label": "üñîçødë_tëst_µ", "metrics": [0.12, 0.45]}
    test_file = tmp_path / "utf8_artifact.json"
    test_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    loaded = json.loads(test_file.read_text(encoding="utf-8"))
    assert loaded == data


def test_late_failure_prevents_publication(isolated_verification_output, tmp_path, monkeypatch) -> None:
    call_count = 0
    real_subprocess_run = vgr.subprocess.run

    # Create dummy artifact files in temporary directory
    art_dir = tmp_path / "fake_artifacts" / "dummy_exp"
    art_dir.mkdir(parents=True, exist_ok=True)
    acq_payload = {
        "requested_labels": 50, "consumed_labels": 50, "distinct_labels": 50,
        "acquired_ids": [f"id_{i}" for i in range(50)],
        "order": [f"id_{i}" for i in range(50)],
    }
    (art_dir / "acquisition.json").write_text(json.dumps(acq_payload), encoding="utf-8")
    mask_payload = {
        "full_pool": {"record_ids": [f"pool_{i}" for i in range(4119)], "mask_id": "m1", "rates": {
            "observed_all_feature_cells_new_missing_rate": 0.1, "newly_missing_cells": 10, "observed_all_feature_cells": 100,
            "observed_history_group_new_missing_rate": 0.2, "observed_history_eligible_cells": 50, "total_missing_cells": 15,
            "natural_missing_cells": 5,
        }},
        "test": {"record_ids": [f"test_{i}" for i in range(8238)], "mask_id": "m2", "rates": {
            "observed_all_feature_cells_new_missing_rate": 0.1, "newly_missing_cells": 10, "observed_all_feature_cells": 100,
            "observed_history_group_new_missing_rate": 0.2, "observed_history_eligible_cells": 50, "total_missing_cells": 15,
            "natural_missing_cells": 5,
        }},
        "acquired_subset": {"record_ids": [f"id_{i}" for i in range(50)], "parent_mask_id": "m1", "rates": {
            "observed_all_feature_cells_new_missing_rate": 0.1, "newly_missing_cells": 10, "observed_all_feature_cells": 100,
            "observed_history_group_new_missing_rate": 0.2, "observed_history_eligible_cells": 50, "total_missing_cells": 15,
            "natural_missing_cells": 5,
        }},
    }
    (art_dir / "masks.json").write_text(json.dumps(mask_payload), encoding="utf-8")

    # Redirect APP artifact lookup in verify_gate2_reproduction
    monkeypatch.setattr(vgr, "APP", tmp_path / "fake_app")
    (tmp_path / "fake_app" / "var" / "artifacts").mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copytree(art_dir, tmp_path / "fake_app" / "var" / "artifacts" / "dummy_exp")

    def fake_subprocess_run(cmd, *args, **kwargs):
        nonlocal call_count
        if cmd[0] == "git":
            return real_subprocess_run(cmd, *args, **kwargs)
        call_count += 1
        if call_count <= 2:
            # Fake successful run for sqlite-first and sqlite-second
            dummy_conditions = {
                c: {
                    "condition_id": f"cid-{c}",
                    "mask_id": "mask-123" if c.startswith("outage_") else None,
                    "metrics": {
                        "brier_score": 0.1,
                        "log_loss": 0.2,
                        "reliability": [{"count": 8238, "mean_probability": 0.5, "positive_fraction": 0.5}],
                    },
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
            dummy = {
                "experiment_id": "dummy_exp",
                "execution_id": f"exec-{call_count}",
                "conditions": dummy_conditions,
                "comparisons": dummy_comparisons,
                "content_hashes": {},
            }
            class FakeSuccess:
                returncode = 0
                stdout = json.dumps(dummy)
                stderr = ""
            return FakeSuccess()
        # Fail on third run (postgres)
        class FakeFail:
            returncode = 1
            stderr = "postgres_network_error"
        return FakeFail()

    monkeypatch.setenv("SHIFTGUARD_TEST_POSTGRES_URL", "postgresql://user:pass@localhost:5432/test")
    monkeypatch.setenv("SHIFTGUARD_EXPECTED_COMMIT", "test_commit")
    monkeypatch.setattr(vgr.subprocess, "run", fake_subprocess_run)

    with pytest.raises(RuntimeError, match="postgres failed: postgres_network_error"):
        vgr.main()

    # Neither the final summary nor intermediate files may be published to output
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


def test_provenance_validation_rejects_dirty() -> None:
    execution_ids = ["e1"]
    audits = {
        "e1": {"provenance": {"git": {"available": True, "dirty": True, "head": "commit123"}}},
    }
    with pytest.raises(AssertionError, match="Working tree was dirty"):
        vgr.validate_execution_provenance(execution_ids, audits, "commit123")


def test_provenance_validation_rejects_unavailable() -> None:
    execution_ids = ["e1"]
    audits = {
        "e1": {"provenance": {"git": {"available": False, "dirty": False, "head": "commit123"}}},
    }
    with pytest.raises(AssertionError, match="Git provenance not available"):
        vgr.validate_execution_provenance(execution_ids, audits, "commit123")


def test_provenance_validation_rejects_wrong_head() -> None:
    execution_ids = ["e1"]
    audits = {
        "e1": {"provenance": {"git": {"available": True, "dirty": False, "head": "wrong_commit"}}},
    }
    with pytest.raises(AssertionError, match="HEAD wrong_commit != expected commit expected_commit"):
        vgr.validate_execution_provenance(execution_ids, audits, "expected_commit")


def test_provenance_validation_rejects_missing_audit() -> None:
    execution_ids = ["e1", "e2"]
    audits = {
        "e1": {"provenance": {"git": {"available": True, "dirty": False, "head": "commit123"}}},
    }
    with pytest.raises(AssertionError, match="Audit missing for execution e2"):
        vgr.validate_execution_provenance(execution_ids, audits, "commit123")
