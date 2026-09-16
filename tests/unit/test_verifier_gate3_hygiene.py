from __future__ import annotations

import os
from pathlib import Path
import pytest

import verification.verify_gate3_reproduction as vg3


def test_gate3_provenance_rejects_non_boolean_or_dirty():
    audits = {
        "exec-1": {
            "provenance": {
                "git": {"available": True, "dirty": False, "head": "commit-123"}
            }
        }
    }
    # Valid
    res = vg3.validate_execution_provenance(["exec-1"], audits, "commit-123")
    assert res["git_available"] is True
    assert res["git_dirty"] is False
    assert res["verified_commit"] == "commit-123"

    # Dirty = True -> reject
    audits_dirty = {
        "exec-1": {
            "provenance": {
                "git": {"available": True, "dirty": True, "head": "commit-123"}
            }
        }
    }
    with pytest.raises(AssertionError, match="dirty must be False"):
        vg3.validate_execution_provenance(["exec-1"], audits_dirty, "commit-123")

    # Dirty = None -> reject
    audits_none = {
        "exec-1": {
            "provenance": {
                "git": {"available": True, "dirty": None, "head": "commit-123"}
            }
        }
    }
    with pytest.raises(AssertionError, match="dirty must be False"):
        vg3.validate_execution_provenance(["exec-1"], audits_none, "commit-123")

    # Head mismatch -> reject
    with pytest.raises(AssertionError, match="HEAD.*!= expected commit"):
        vg3.validate_execution_provenance(["exec-1"], audits, "wrong-commit")


def test_gate3_verifier_rejects_missing_postgres(monkeypatch, tmp_path):
    monkeypatch.delenv("SHIFTGUARD_TEST_POSTGRES_URL", raising=False)
    monkeypatch.setenv("SHIFTGUARD_VERIFICATION_OUTPUT", str(tmp_path))

    with pytest.raises(RuntimeError, match="SHIFTGUARD_TEST_POSTGRES_URL is required"):
        vg3.main()


def test_gate3_verifier_invalidates_stale_pass(monkeypatch, tmp_path):
    monkeypatch.delenv("SHIFTGUARD_TEST_POSTGRES_URL", raising=False)
    monkeypatch.setenv("SHIFTGUARD_VERIFICATION_OUTPUT", str(tmp_path))

    stale_file = tmp_path / "verification.json"
    stale_file.write_text('{"status": "stale_pass"}', encoding="utf-8")
    assert stale_file.is_file()

    with pytest.raises(RuntimeError):
        vg3.main()

    # The stale file must have been deleted before failing
    assert not stale_file.exists()
