"""Independent CLI, artifact, storage, and 4-payload verification for Gate 3 stress engine candidate."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile

import psycopg


APP = Path(__file__).resolve().parents[1]
ROOT = APP.parent
DEFAULT_OUTPUT = ROOT / "verification" / "gate3"

REQUIRED_PAYLOADS = ("budget_curve", "pattern_vs_rate", "reliability", "decision_loss")
REQUIRED_METHODS = (
    "raw",
    "source_temperature",
    "source_remasked_temperature",
    "source_fraction_binned_temperature",
    "target_temperature",
    "target_platt_logodds",
    "target_beta",
    "target_isotonic",
)


def get_output_dir() -> Path:
    if "SHIFTGUARD_VERIFICATION_OUTPUT" in os.environ:
        return Path(os.environ["SHIFTGUARD_VERIFICATION_OUTPUT"])
    return DEFAULT_OUTPUT


def get_expected_commit() -> str:
    if "SHIFTGUARD_EXPECTED_COMMIT" in os.environ:
        return os.environ["SHIFTGUARD_EXPECTED_COMMIT"].strip()
    res = subprocess.run(
        ["git", "-c", "safe.directory=*", "rev-parse", "HEAD"],
        cwd=APP, capture_output=True, text=True, encoding="utf-8",
    )
    if res.returncode != 0:
        raise RuntimeError(f"Failed to determine Git HEAD: {res.stderr}")
    return res.stdout.strip()


def validate_execution_provenance(
    execution_ids: list[str],
    audits: dict[str, dict],
    expected_commit: str,
) -> dict[str, object]:
    for execution_id in execution_ids:
        if execution_id not in audits:
            raise AssertionError(f"Audit missing for execution {execution_id}")
        audit = audits[execution_id]
        git_info = audit.get("provenance", {}).get("git", {})
        if git_info.get("available") is not True:
            raise AssertionError(
                f"Git provenance available must be True for execution {execution_id}, got {git_info.get('available')!r}"
            )
        if git_info.get("dirty") is not False:
            raise AssertionError(
                f"Git provenance dirty must be False for execution {execution_id}, got {git_info.get('dirty')!r}"
            )
        if git_info.get("head") != expected_commit:
            raise AssertionError(
                f"Execution {execution_id} HEAD {git_info.get('head')} != expected commit {expected_commit}"
            )
    return {
        "git_available": True,
        "git_dirty": False,
        "verified_commit": expected_commit,
    }


def main() -> None:
    output_dir = get_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    canonical_verification = output_dir / "verification.json"
    if canonical_verification.exists():
        canonical_verification.unlink()

    if "SHIFTGUARD_TEST_POSTGRES_URL" not in os.environ:
        raise RuntimeError("SHIFTGUARD_TEST_POSTGRES_URL is required for Gate 3 reproduction verification")
    postgres_url = os.environ["SHIFTGUARD_TEST_POSTGRES_URL"]
    expected_commit = get_expected_commit()
    verifier_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

    with tempfile.TemporaryDirectory() as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        database = temp_dir / "reproduction.db"
        sqlite_url = "sqlite:///" + database.as_posix()
        temp_outputs: dict[str, Path] = {}
        runs = []

        for name, url in (("sqlite-first", sqlite_url), ("sqlite-second", sqlite_url), ("postgres", postgres_url)):
            env = os.environ.copy()
            env["SHIFTGUARD_ENVIRONMENT"] = "hosted" if name == "postgres" else "local"
            result = subprocess.run(
                [
                    str(APP / ".venv/Scripts/shiftguard.exe"),
                    "--db-url", url,
                    "run", "--config", "configs/bank-stress.yaml",
                ],
                cwd=APP, env=env, capture_output=True, text=True, encoding="utf-8",
            )
            if result.returncode != 0:
                raise RuntimeError(f"{name} failed: {result.stderr}")

            data = json.loads(result.stdout)
            experiment_id = data["experiment_id"]
            content_hashes = data["content_hashes"]
            artifact_root = APP / "var/artifacts" / experiment_id
            payload_root = artifact_root / "payloads"

            # 1. Verify byte hashes of all generated artifacts
            for key, digest in content_hashes.items():
                if key == "logical_content":
                    continue
                if key in REQUIRED_PAYLOADS:
                    target_file = payload_root / f"{key}.json"
                else:
                    target_file = artifact_root / f"{key}.json"
                assert target_file.is_file(), f"Artifact file missing: {target_file}"
                actual_hash = hashlib.sha256(target_file.read_bytes()).hexdigest()
                assert actual_hash == digest, f"Artifact hash mismatch for {key}: expected {digest}, got {actual_hash}"

            # 2. Verify payloads structure
            bc_data = json.loads((payload_root / "budget_curve.json").read_text(encoding="utf-8"))
            assert "scenarios" in bc_data
            pvr_data = json.loads((payload_root / "pattern_vs_rate.json").read_text(encoding="utf-8"))
            assert "matching_report" in pvr_data
            assert pvr_data["matching_report"]["matching_strategy"] == "exact_realized_rate"
            rel_data = json.loads((payload_root / "reliability.json").read_text(encoding="utf-8"))
            assert "scenarios" in rel_data
            dl_data = json.loads((payload_root / "decision_loss.json").read_text(encoding="utf-8"))
            assert "scenarios" in dl_data

            temp_file = temp_dir / f"{name}.json"
            temp_file.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            temp_outputs[name] = temp_file
            runs.append(data)

        # Parity checks across 3 runs
        first = runs[0]
        for run in runs[1:]:
            for key in ("experiment_id", "content_hashes"):
                assert run[key] == first[key], f"Run parity failure on {key}"

        execution_ids = [run["execution_id"] for run in runs]
        assert len(set(execution_ids)) == 3, f"Expected 3 distinct execution UUIDs, got {execution_ids}"

        # Database parity check between SQLite and PostgreSQL
        sqlite_conn = sqlite3.connect(database)
        try:
            sqlite_payload = sqlite_conn.execute("SELECT payload_json FROM experiments WHERE id = ?", (first["experiment_id"],)).fetchone()[0]
            sqlite_audits = sqlite_conn.execute("SELECT execution_id, audit_json FROM experiment_executions WHERE experiment_id = ?", (first["experiment_id"],)).fetchall()
        finally:
            sqlite_conn.close()

        with psycopg.connect(postgres_url) as connection:
            postgres_payload = connection.execute("SELECT payload_json FROM experiments WHERE id = %s", (first["experiment_id"],)).fetchone()[0]
            postgres_audits = connection.execute("SELECT execution_id, audit_json FROM experiment_executions WHERE experiment_id = %s", (first["experiment_id"],)).fetchall()

        assert json.loads(sqlite_payload) == json.loads(postgres_payload), "SQLite and PostgreSQL experiments table payload mismatch"
        audits = {row[0]: json.loads(row[1]) for row in sqlite_audits + postgres_audits}
        assert all(execution in audits for execution in execution_ids), "Missing audits for executions"

        provenance_summary = validate_execution_provenance(execution_ids, audits, expected_commit)
        provenance_summary["verifier_sha256"] = verifier_sha256

        summary = {
            "status": "passed",
            "gate": 3,
            "experiment_id": first["experiment_id"],
            "execution_ids": execution_ids,
            "identical_artifact_hashes": first["content_hashes"],
            "payload_keys": list(REQUIRED_PAYLOADS),
            "condition_count": first.get("condition_count"),
            "sqlite_and_postgres_payloads_equal": True,
            "execution_audits": {key: audits[key] for key in execution_ids},
            "verified_provenance": provenance_summary,
        }

        for name, temp_file in temp_outputs.items():
            target = output_dir / f"{name}.json"
            temp_file.replace(target)

        temp_verif = temp_dir / "verification.json"
        temp_verif.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temp_verif.replace(canonical_verification)
        print(json.dumps({
            "status": "passed",
            "gate": 3,
            "experiment_id": first["experiment_id"],
            "executions": execution_ids,
            "verified_commit": expected_commit,
        }))


if __name__ == "__main__":
    main()
