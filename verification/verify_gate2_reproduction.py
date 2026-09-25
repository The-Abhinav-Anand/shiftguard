"""Independent CLI/artifact/storage verification for Gate 2 outage recovery candidate."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
from uuid import uuid4

import psycopg

from shiftguard.experiments.ids import stable_hash


APP = Path(__file__).resolve().parents[1]
ROOT = APP.parent
DEFAULT_OUTPUT = ROOT / "verification" / "gate2"
CONDITIONS = {
    "no_outage_raw", "no_outage_source_temperature", "outage_raw",
    "outage_source_temperature", "outage_target_temperature",
}
GATE2_REQUIRED_HASH_KEYS = {
    "config", "seeds", "masks", "acquisition", "metadata", "conditions", "comparisons", "logical_content",
}
RUN_NAMES = ("sqlite-first", "sqlite-second", "postgres")


def connect_postgres(postgres_url: str):
    """Connect with psycopg using canonical or SQLAlchemy psycopg URLs."""
    if postgres_url.startswith("postgresql+psycopg://"):
        postgres_url = "postgresql://" + postgres_url.removeprefix("postgresql+psycopg://")
    return psycopg.connect(postgres_url)


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


def validate_manifest_content_hashes(
    content_hashes: dict[str, str],
    artifact_root: Path,
) -> None:
    """Verify exact match against GATE2_REQUIRED_HASH_KEYS and byte digests of all artifacts."""
    if set(content_hashes.keys()) != GATE2_REQUIRED_HASH_KEYS:
        missing = sorted(GATE2_REQUIRED_HASH_KEYS - set(content_hashes.keys()))
        extra = sorted(set(content_hashes.keys()) - GATE2_REQUIRED_HASH_KEYS)
        raise AssertionError(
            f"content_hashes missing required Gate 2 artifact keys: missing={missing}, extra={extra}"
        )

    for key, digest in content_hashes.items():
        if key == "logical_content":
            continue
        target_file = artifact_root / f"{key}.json"
        if not target_file.is_file():
            raise AssertionError(f"Artifact file missing: {target_file}")
        actual_hash = hashlib.sha256(target_file.read_bytes()).hexdigest()
        if actual_hash != digest:
            raise AssertionError(f"Artifact hash mismatch for {key}: expected {digest}, got {actual_hash}")


def validate_condition_ids_preimages(conditions: dict[str, dict[str, object]]) -> None:
    """Independently recompute and verify condition IDs from their exact preimages."""
    for cond_key, cond in conditions.items():
        preimage = {k: v for k, v in cond.items() if k != "condition_id"}
        expected_cid = stable_hash(preimage)[:24]
        if cond.get("condition_id") != expected_cid:
            raise AssertionError(
                f"Condition {cond_key} ID mismatch: expected {expected_cid}, got {cond.get('condition_id')}"
            )


def validate_comparison_ids_preimages(
    comparisons: dict[str, dict[str, object]],
    condition_ids: set[str],
) -> None:
    """Independently recompute and verify comparison IDs from their exact preimages."""
    for comp_key, comp in comparisons.items():
        preimage = {k: v for k, v in comp.items() if k != "comparison_id"}
        expected_comp_id = stable_hash(preimage)[:24]
        if comp.get("comparison_id") != expected_comp_id:
            raise AssertionError(
                f"Comparison {comp_key} ID mismatch: expected {expected_comp_id}, got {comp.get('comparison_id')}"
            )
        if comp.get("earlier") not in condition_ids or comp.get("later") not in condition_ids:
            raise AssertionError(f"Comparison {comp_key} references invalid condition ID")


def validate_database_projections(
    payload: dict[str, object],
    artifact_root: Path,
    reported_conditions: dict[str, dict[str, object]],
    reported_comparisons: dict[str, dict[str, object]],
) -> None:
    """Compare stored database projections with on-disk artifacts and reported outputs."""
    projections = {
        "config": (artifact_root / "config.json", payload.get("config")),
        "seeds": (artifact_root / "seeds.json", payload.get("seeds")),
        "masks": (artifact_root / "masks.json", payload.get("masks")),
        "acquisition": (artifact_root / "acquisition.json", payload.get("acquisition")),
        "metadata": (artifact_root / "metadata.json", payload.get("metadata")),
        "conditions": (artifact_root / "conditions.json", payload.get("conditions")),
        "comparisons": (artifact_root / "comparisons.json", payload.get("comparisons")),
    }
    for proj_name, (proj_file, proj_db) in projections.items():
        if not proj_file.is_file():
            raise AssertionError(f"Projection file missing: {proj_file}")
        file_content = json.loads(proj_file.read_text(encoding="utf-8"))
        if file_content != proj_db:
            raise AssertionError(f"Database projection {proj_name} does not match saved artifact")

    if payload.get("conditions") != reported_conditions:
        raise AssertionError("Database projection conditions do not match reported output")
    if payload.get("comparisons") != reported_comparisons:
        raise AssertionError("Database projection comparisons do not match reported output")


def validate_logical_content_and_experiment_id(
    payload: dict[str, object],
    content_hashes: dict[str, str],
    experiment_id: str,
) -> None:
    """Recompute logical content digest and experiment ID from database payload."""
    clean_payload = {
        k: v for k, v in payload.items()
        if k not in ("execution_id", "content_hashes", "experiment_id")
    }
    recomputed_logical = stable_hash(clean_payload)
    reported_logical = content_hashes.get("logical_content")
    if reported_logical != recomputed_logical:
        raise AssertionError(
            f"Logical content digest mismatch: expected {recomputed_logical}, got {reported_logical}"
        )
    recomputed_exp_id = recomputed_logical[:24]
    if experiment_id != recomputed_exp_id:
        raise AssertionError(
            f"Experiment ID mismatch: expected {recomputed_exp_id}, got {experiment_id}"
        )


def main() -> None:
    output_dir = get_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    attempts_dir = output_dir / "attempts"
    attempts_dir.mkdir(parents=True, exist_ok=True)

    canonical_verification = output_dir / "verification.json"

    attempt_timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    attempt_id = f"attempt-{attempt_timestamp}-{uuid4().hex[:8]}"
    attempt_dir = attempts_dir / attempt_id
    attempt_dir.mkdir(parents=True, exist_ok=True)
    current_attempt_pointer = output_dir / "current_attempt.json"

    def _write_current_attempt(record: dict[str, object]) -> None:
        tmp = output_dir / f".tmp-current_attempt-{uuid4().hex[:6]}.json"
        tmp.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(current_attempt_pointer)

    expected_commit = "unknown"
    _write_current_attempt({
        "candidate": expected_commit,
        "attempt_id": attempt_id,
        "status": "IN_PROGRESS",
        "started_at": datetime.now(timezone.utc).isoformat(),
    })

    try:
        # Select the new attempt before archiving: an archive failure cannot leave
        # a previous PASS selected. Preserve actual output names and older aliases.
        legacy_candidates = ("verification.json", *(f"{name}.json" for name in RUN_NAMES),
                             "run-1.json", "run-2.json", "run-3.json")
        existing_legacy_files = [name for name in legacy_candidates if (output_dir / name).is_file()]
        if existing_legacy_files:
            archive_id = f"legacy-bundle-{attempt_timestamp}-{uuid4().hex[:8]}"
            archive_dir = attempts_dir / archive_id
            archive_dir.mkdir(parents=True, exist_ok=False)
            for name in existing_legacy_files:
                shutil.move(str(output_dir / name), str(archive_dir / name))
            (archive_dir / "archive_metadata.json").write_text(
                json.dumps({
                    "archived_at": datetime.now(timezone.utc).isoformat(),
                    "archived_files": existing_legacy_files,
                }, indent=2) + "\n", encoding="utf-8",
            )

        expected_commit = get_expected_commit()
        _write_current_attempt({
            "candidate": expected_commit,
            "attempt_id": attempt_id,
            "status": "IN_PROGRESS",
            "started_at": datetime.now(timezone.utc).isoformat(),
        })

        if "SHIFTGUARD_TEST_POSTGRES_URL" not in os.environ:
            raise RuntimeError("SHIFTGUARD_TEST_POSTGRES_URL is required for Gate 2 reproduction verification")
        postgres_url = os.environ["SHIFTGUARD_TEST_POSTGRES_URL"]
        verifier_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = Path(temp_dir_str)
            database = temp_dir / "reproduction.db"
            sqlite_url = "sqlite:///" + database.as_posix()
            temp_outputs: dict[str, Path] = {}
            runs = []
            for name, url in zip(RUN_NAMES, (sqlite_url, sqlite_url, postgres_url), strict=True):
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
                artifact_root = APP / "var/artifacts" / data["experiment_id"]

                # Exact key validation and byte hash validation
                validate_manifest_content_hashes(data["content_hashes"], artifact_root)

                # Preimage validation for conditions and comparisons
                validate_condition_ids_preimages(data["conditions"])
                validate_comparison_ids_preimages(data["comparisons"], set(by_id.keys()))

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
                temp_file.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
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
            with connect_postgres(postgres_url) as connection:
                postgres_payload = connection.execute("SELECT payload_json FROM experiments WHERE id = %s", (first["experiment_id"],)).fetchone()[0]
                postgres_audits = connection.execute("SELECT execution_id, audit_json FROM experiment_executions WHERE experiment_id = %s", (first["experiment_id"],)).fetchall()
            assert json.loads(sqlite_payload) == json.loads(postgres_payload)
            db_payload = json.loads(sqlite_payload)

            # Reconstruct and validate database projections against disk artifacts and reported output
            artifact_root = APP / "var/artifacts" / first["experiment_id"]
            validate_database_projections(db_payload, artifact_root, first["conditions"], first["comparisons"])

            # Recompute logical content and experiment ID from database payload
            validate_logical_content_and_experiment_id(db_payload, first["content_hashes"], first["experiment_id"])

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
                attempt_target = attempt_dir / f"{name}.json"
                temp_file.replace(attempt_target)
                (output_dir / f"{name}.json").write_text(attempt_target.read_text(encoding="utf-8"), encoding="utf-8")

            summary_json = json.dumps(summary, indent=2, ensure_ascii=False) + "\n"
            (attempt_dir / "verification.json").write_text(summary_json, encoding="utf-8")
            temp_verif = temp_dir / "verification.json"
            temp_verif.write_text(summary_json, encoding="utf-8")
            temp_verif.replace(canonical_verification)

            _write_current_attempt({
                "candidate": expected_commit,
                "attempt_id": attempt_id,
                "status": "PASS",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "experiment_id": first["experiment_id"],
            })

            print(json.dumps({"status": "passed", "experiment_id": first["experiment_id"], "executions": execution_ids, "verified_commit": expected_commit}))

    except Exception as exc:
        _write_current_attempt({
            "candidate": expected_commit,
            "attempt_id": attempt_id,
            "status": "FAILED",
            "failed_at": datetime.now(timezone.utc).isoformat(),
            "error": str(exc),
        })
        raise


if __name__ == "__main__":
    main()
