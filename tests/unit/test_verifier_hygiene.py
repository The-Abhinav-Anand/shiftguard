from __future__ import annotations

import json
import os
import sys
from pathlib import Path
import pytest

VERIFICATION_DIR = Path(__file__).resolve().parents[3] / "verification"
if str(VERIFICATION_DIR) not in sys.path:
    sys.path.insert(0, str(VERIFICATION_DIR))

import verify_gate2_reproduction as vgr


def test_verifier_requires_postgres_url(monkeypatch) -> None:
    monkeypatch.delenv("SHIFTGUARD_TEST_POSTGRES_URL", raising=False)
    with pytest.raises(RuntimeError, match="SHIFTGUARD_TEST_POSTGRES_URL is required for Gate 2 reproduction verification"):
        vgr.main()


def test_stale_verification_json_unlinked_on_start(tmp_path, monkeypatch) -> None:
    fake_output = tmp_path / "gate2"
    fake_output.mkdir(parents=True, exist_ok=True)
    stale_file = fake_output / "verification.json"
    stale_file.write_text('{"status": "stale_pass"}', encoding="utf-8")
    assert stale_file.exists()

    monkeypatch.setattr(vgr, "OUTPUT", fake_output)
    monkeypatch.delenv("SHIFTGUARD_TEST_POSTGRES_URL", raising=False)

    with pytest.raises(RuntimeError, match="SHIFTGUARD_TEST_POSTGRES_URL"):
        vgr.main()

    # Must be unlinked even if verifier subsequently fails
    assert not stale_file.exists()


def test_utf8_json_read_preserves_characters(tmp_path) -> None:
    data = {"name": "üñîçødë_tëst", "count": 50}
    test_file = tmp_path / "test_utf8.json"
    test_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    loaded = json.loads(test_file.read_text(encoding="utf-8"))
    assert loaded == data


def test_verifier_isolates_sqlite_and_atomic_outputs(tmp_path, monkeypatch) -> None:
    fake_output = tmp_path / "gate2"
    fake_output.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(vgr, "OUTPUT", fake_output)
    monkeypatch.setenv("SHIFTGUARD_TEST_POSTGRES_URL", "postgresql://fake/test")

    class FakeResult:
        returncode = 1
        stderr = "simulated_failure"

    monkeypatch.setattr(vgr.subprocess, "run", lambda *args, **kwargs: FakeResult())

    with pytest.raises(RuntimeError, match="simulated_failure"):
        vgr.main()

    # reproduction.db must NOT be created in OUTPUT
    assert not (fake_output / "reproduction.db").exists()
    # intermediate and final files must NOT be published in OUTPUT
    assert not (fake_output / "sqlite-first.json").exists()
    assert not (fake_output / "verification.json").exists()
