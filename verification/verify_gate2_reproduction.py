"""Independent CLI/artifact/storage verification for Gate 2 outage recovery candidate."""
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
DEFAULT_OUTPUT = ROOT / "verification" / "gate2"
CONDITIONS = {
    "no_outage_raw", "no_outage_source_temperature", "outage_raw",
    "outage_source_temperature", "outage_target_temperature",
}


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
        if not git_info.get("available"):
            raise AssertionError(f"Git provenance not available for execution {execution_id}")
        if git_info.get("dirty"):
            raise AssertionError(f"Working tree was dirty during execution {execution_id}")
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
        raise RuntimeError("SHIFTGUARD_TEST_POSTGRES_URL is required for Gate 2 reproduction verification")
    postgres_url = os.environ["SHIFTGUARD_TEST_POSTGRES_URL"]
    expected_commit = get_expected_commit()
    verifier_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

    with tempfile.TemporaryDirectory() as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        database = temp_dir / "reproduction.db"
        sqlite_url = "sqlite:///" + database.as_posix()
        temp_outputs: dict[str, Path] = {}
        runs = []
        for name, url in (("sqlite-first", sqlite_url), ("sqlite-second", sqlite_url),
                          ("postgres", postgres_url)):
            env = os.environ.copy()
            env["SHIFTGUARD_ENVIRONMENT"] = "hosted" if name == "postgres" else "local"
            result = subprocess.run(
                [str(APP / ".venv/Scripts/shiftguard.exe"), "--db-url", url,
                 "run", "--config", "configs/bank-outage-50.yaml"],
                cwd=APP, env=env, capture_output=True, text=True, encoding="utf-8",
            )
            if result.returncode:
                raise RuntimeError(f"{name} failed: {result.stderr}")
            data = json.loads(result.stdout)
            assert set(data["conditions"]) == CONDITIONS
            assert len(data["comparisons"]) == 6
            by_id = {condition["condition_id"]: condition for condition in data["conditions"].values()}
            assert len(by_id) == 5
            for condition in by_id.values():
                metrics = condition["metrics"]
                assert math.isfinite(metrics["brier_score"]) and 0 <= metrics["brier_score"] <= 1
                assert math.isfinite(metrics["log_loss"]) and metrics["log_loss"] >= 0
                assert sum(bin_["count"] for bin_ in metrics["reliability"]) == 8238
                for bin_ in metrics["reliability"]:
                    if bin_["count"] == 0:
                        assert bin_["mean_probability"] is bin_["positive_fraction"] is None
            for comparison in data["comparisons"].values():
                for metric, delta in comparison["deltas"].items():
                    expected = by_id[comparison["later"]]["metrics"][metric] - by_id[comparison["earlier"]]["metrics"][metric]
                    assert math.isclose(delta, expected, abs_tol=1e-15)
            mask_ids = {data["conditions"][key]["mask_id"] for key in CONDITIONS
                        if key.startswith("outage_")}
            assert len(mask_ids) == 1 and None not in mask_ids
            artifact_root = APP / "var/artifacts" / data["experiment_id"]
            for key, digest in data["content_hashes"].items():
                if key != "logical_content":
                    assert hashlib.sha256((artifact_root / f"{key}.json").read_bytes()).hexdigest() == digest
            acquisition = json.loads((artifact_root / "acquisition.json").read_text(encoding="utf-8"))
            assert acquisition["requested_labels"] == acquisition["consumed_labels"] == acquisition["distinct_labels"] == 50
            assert len(set(acquisition["acquired_ids"])) == 50
            assert acquisition["acquired_ids"] == acquisition["order"][:50]
            masks = json.loads((artifact_root / "masks.json").read_text(encoding="utf-8"))
            assert len(masks["full_pool"]["record_ids"]) == 4119
            assert len(masks["test"]["record_ids"]) == 8238
            assert set(masks["full_pool"]["record_ids"]).isdisjoint(masks["test"]["record_ids"])
            assert masks["acquired_subset"]["record_ids"] == acquisition["acquired_ids"]
            assert masks["acquired_subset"]["parent_mask_id"] == masks["full_pool"]["mask_id"]
            for mask in masks.values():
                rates = mask["rates"]
                assert math.isclose(rates["observed_all_feature_cells_new_missing_rate"], rates["newly_missing_cells"] / rates["observed_all_feature_cells"])
                assert math.isclose(rates["observed_history_group_new_missing_rate"], rates["newly_missing_cells"] / rates["observed_history_eligible_cells"])
                assert rates["total_missing_cells"] == rates["natural_missing_cells"] + rates["newly_missing_cells"]
            assert "y" not in acquisition and "labels" not in acquisition
            temp_file = temp_dir / f"{name}.json"
            temp_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            temp_outputs[name] = temp_file
            runs.append(data)
        first = runs[0]
        for run in runs[1:]:
            for key in ("experiment_id", "conditions", "comparisons", "content_hashes"):
                assert run[key] == first[key], key
        execution_ids = [run["execution_id"] for run in runs]
        assert len(set(execution_ids)) == 3
        sqlite_conn = sqlite3.connect(database)
        try:
            sqlite_payload = sqlite_conn.execute("SELECT payload_json FROM experiments WHERE id = ?", (first["experiment_id"],)).fetchone()[0]
            sqlite_audits = sqlite_conn.execute("SELECT execution_id, audit_json FROM experiment_executions WHERE experiment_id = ?", (first["experiment_id"],)).fetchall()
        finally:
            sqlite_conn.close()
        with psycopg.connect(postgres_url) as connection:
            postgres_payload = connection.execute("SELECT payload_json FROM experiments WHERE id = %s", (first["experiment_id"],)).fetchone()[0]
            postgres_audits = connection.execute("SELECT execution_id, audit_json FROM experiment_executions WHERE experiment_id = %s", (first["experiment_id"],)).fetchall()
        assert json.loads(sqlite_payload) == json.loads(postgres_payload)
        audits = {row[0]: json.loads(row[1]) for row in sqlite_audits + postgres_audits}
        assert all(execution in audits for execution in execution_ids)

        provenance_summary = validate_execution_provenance(execution_ids, audits, expected_commit)
        provenance_summary["verifier_sha256"] = verifier_sha256

        summary = {
            "status": "passed", "experiment_id": first["experiment_id"],
            "execution_ids": execution_ids, "identical_artifact_hashes": first["content_hashes"],
            "conditions": first["conditions"], "comparisons": first["comparisons"],
            "sqlite_and_postgres_payloads_equal": True,
            "execution_audits": {key: audits[key] for key in execution_ids},
            "verified_provenance": provenance_summary,
        }

        for name, temp_file in temp_outputs.items():
            target = output_dir / f"{name}.json"
            temp_file.replace(target)

        temp_verif = temp_dir / "verification.json"
        temp_verif.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        temp_verif.replace(canonical_verification)
        print(json.dumps({"status": "passed", "experiment_id": first["experiment_id"], "executions": execution_ids, "verified_commit": expected_commit}))


if __name__ == "__main__":
    main()
