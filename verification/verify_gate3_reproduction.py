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
REQUIRED_PREDICTORS = ("logistic_regression", "random_forest")
REQUIRED_SCENARIOS = ("baseline", "history_block_0_50", "mcar_matched_history", "mcar_0_10", "mcar_0_30")
REQUIRED_BUDGETS = (0, 25, 50, 100, 200)
EXPECTED_EVAL_ROWS = 8238
EXPECTED_CONDITION_COUNT = 400


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


def validate_scientific_payloads(
    artifact_root: Path,
    payload_root: Path,
    conditions_data: dict[str, dict[str, object]],
) -> dict[str, object]:
    """Validate full 400-condition scientific matrix, metric bounds, matching semantics, and evaluation counts."""
    if not conditions_data:
        raise AssertionError("Conditions data must not be empty")
    if len(conditions_data) != EXPECTED_CONDITION_COUNT:
        raise AssertionError(f"Expected {EXPECTED_CONDITION_COUNT} conditions, got {len(conditions_data)}")

    for p in REQUIRED_PREDICTORS:
        for s in REQUIRED_SCENARIOS:
            for b in REQUIRED_BUDGETS:
                for m in REQUIRED_METHODS:
                    cond_key = f"{p}__{s}__b{b}__{m}"
                    if cond_key not in conditions_data:
                        raise AssertionError(f"Missing required condition: {cond_key}")
                    c = conditions_data[cond_key]
                    if c.get("predictor") != p:
                        raise AssertionError(f"Condition {cond_key} has wrong predictor: {c.get('predictor')}")
                    if c.get("scenario") != s:
                        raise AssertionError(f"Condition {cond_key} has wrong scenario: {c.get('scenario')}")
                    if c.get("budget") != b:
                        raise AssertionError(f"Condition {cond_key} has wrong budget: {c.get('budget')}")
                    if c.get("requested_method") != m:
                        raise AssertionError(f"Condition {cond_key} has wrong requested_method: {c.get('requested_method')}")
                    if c.get("status") not in ("scored", "failed"):
                        raise AssertionError(f"Condition {cond_key} has invalid status: {c.get('status')}")
                    if c.get("status") == "scored":
                        met = c.get("metrics")
                        if not met:
                            raise AssertionError(f"Scored condition {cond_key} has no metrics")
                        for k in ("brier_score", "log_loss", "ece", "roc_auc", "average_precision"):
                            v = met.get(k)
                            if v is None or not math.isfinite(float(v)):
                                raise AssertionError(f"Condition {cond_key} metric {k} is invalid: {v}")
                        if not (0.0 <= float(met["brier_score"]) <= 1.0):
                            raise AssertionError(f"Condition {cond_key} brier_score out of bounds [0, 1]: {met['brier_score']}")
                        if float(met["log_loss"]) < 0.0:
                            raise AssertionError(f"Condition {cond_key} log_loss cannot be negative: {met['log_loss']}")
                        if not (0.0 <= float(met["ece"]) <= 1.0):
                            raise AssertionError(f"Condition {cond_key} ece out of bounds [0, 1]: {met['ece']}")
                        if not (0.0 <= float(met["roc_auc"]) <= 1.0):
                            raise AssertionError(f"Condition {cond_key} roc_auc out of bounds [0, 1]: {met['roc_auc']}")
                        if not (0.0 <= float(met["average_precision"]) <= 1.0):
                            raise AssertionError(f"Condition {cond_key} average_precision out of bounds [0, 1]: {met['average_precision']}")
                        if not met.get("decision_loss"):
                            raise AssertionError(f"Condition {cond_key} decision_loss is empty")

    # 1. budget_curve
    bc_file = payload_root / "budget_curve.json"
    if not bc_file.is_file():
        raise AssertionError("Artifact budget_curve.json is missing")
    bc_data = json.loads(bc_file.read_text(encoding="utf-8"))
    scenarios = bc_data.get("scenarios", {})
    if not scenarios:
        raise AssertionError("budget_curve.json has empty scenarios")
    for p in REQUIRED_PREDICTORS:
        for s in REQUIRED_SCENARIOS:
            ps_key = f"{p}__{s}"
            if ps_key not in scenarios:
                raise AssertionError(f"Missing scenario in budget_curve: {ps_key}")
            for m in REQUIRED_METHODS:
                if m not in scenarios[ps_key]:
                    raise AssertionError(f"Missing method {m} in budget_curve for {ps_key}")
                points = scenarios[ps_key][m]
                if len(points) != len(REQUIRED_BUDGETS):
                    raise AssertionError(f"Expected {len(REQUIRED_BUDGETS)} points in budget_curve for {ps_key}/{m}, got {len(points)}")

    # 2. pattern_vs_rate
    pvr_file = payload_root / "pattern_vs_rate.json"
    if not pvr_file.is_file():
        raise AssertionError("Artifact pattern_vs_rate.json is missing")
    pvr_data = json.loads(pvr_file.read_text(encoding="utf-8"))
    mr = pvr_data.get("matching_report", {})
    if mr.get("matching_strategy") != "bernoulli_matched_rate":
        raise AssertionError(f"pattern_vs_rate matching_strategy must be 'bernoulli_matched_rate', got {mr.get('matching_strategy')!r}")
    if mr.get("matching_status") not in ("within_tolerance", "exact_match"):
        raise AssertionError(f"pattern_vs_rate matching_status must be 'within_tolerance' or 'exact_match', got {mr.get('matching_status')!r}")
    if mr.get("comparison_qualified") is not True:
        raise AssertionError(f"pattern_vs_rate comparison_qualified must be True, got {mr.get('comparison_qualified')!r}")
    comparisons = pvr_data.get("comparisons", {})
    for p in REQUIRED_PREDICTORS:
        if p not in comparisons:
            raise AssertionError(f"Missing predictor {p} in pattern_vs_rate comparisons")
        methods = comparisons[p].get("methods", {})
        for m in REQUIRED_METHODS:
            if m not in methods:
                raise AssertionError(f"Missing method {m} in pattern_vs_rate comparisons for {p}")
            m_comp = methods[m]
            if "available" not in m_comp:
                raise AssertionError(f"Missing 'available' key in comparison for {p}/{m}")
            if m_comp["available"] is True:
                if m_comp.get("delta_brier") is None or not math.isfinite(float(m_comp["delta_brier"])):
                    raise AssertionError(f"Available comparison {p}/{m} missing finite delta_brier")

    # 3. reliability
    rel_file = payload_root / "reliability.json"
    if not rel_file.is_file():
        raise AssertionError("Artifact reliability.json is missing")
    rel_data = json.loads(rel_file.read_text(encoding="utf-8"))
    if not rel_data.get("scenarios"):
        raise AssertionError("reliability.json has empty scenarios")
    for scen_key, methods_dict in rel_data["scenarios"].items():
        for m, m_data in methods_dict.items():
            bins = m_data.get("reliability_bins")
            if bins:
                total_samples = sum(b.get("count", 0) for b in bins)
                if total_samples != EXPECTED_EVAL_ROWS:
                    raise AssertionError(f"Reliability diagram in {scen_key}/{m} has total count {total_samples} != {EXPECTED_EVAL_ROWS}")

    # 4. decision_loss
    dl_file = payload_root / "decision_loss.json"
    if not dl_file.is_file():
        raise AssertionError("Artifact decision_loss.json is missing")
    dl_data = json.loads(dl_file.read_text(encoding="utf-8"))
    if not dl_data.get("scenarios"):
        raise AssertionError("decision_loss.json has empty scenarios")

    return {
        "condition_count": len(conditions_data),
        "scientific_matrix_verified": True,
        "evaluator_row_count_verified": True,
        "matching_strategy_verified": True,
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

            # 2. Read and validate conditions.json and scientific payloads
            conditions_file = artifact_root / "conditions.json"
            assert conditions_file.is_file(), "conditions.json missing"
            conditions_data = json.loads(conditions_file.read_text(encoding="utf-8"))
            validate_scientific_payloads(artifact_root, payload_root, conditions_data)

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
            sqlite_payload_raw = sqlite_conn.execute("SELECT payload_json FROM experiments WHERE id = ?", (first["experiment_id"],)).fetchone()[0]
            sqlite_audits = sqlite_conn.execute("SELECT execution_id, audit_json FROM experiment_executions WHERE experiment_id = ?", (first["experiment_id"],)).fetchall()
        finally:
            sqlite_conn.close()

        with psycopg.connect(postgres_url) as connection:
            postgres_payload_raw = connection.execute("SELECT payload_json FROM experiments WHERE id = %s", (first["experiment_id"],)).fetchone()[0]
            postgres_audits = connection.execute("SELECT execution_id, audit_json FROM experiment_executions WHERE experiment_id = %s", (first["experiment_id"],)).fetchall()

        sqlite_payload = json.loads(sqlite_payload_raw)
        postgres_payload = json.loads(postgres_payload_raw)
        assert sqlite_payload == postgres_payload, "SQLite and PostgreSQL experiments table payload mismatch"

        # Database payload equality with saved artifacts
        first_art_root = APP / "var/artifacts" / first["experiment_id"]
        first_pay_root = first_art_root / "payloads"
        first_conditions = json.loads((first_art_root / "conditions.json").read_text(encoding="utf-8"))
        assert sqlite_payload["conditions"] == first_conditions, "Database conditions payload does not match conditions.json"
        assert sqlite_payload["payloads"]["budget_curve"] == json.loads((first_pay_root / "budget_curve.json").read_text(encoding="utf-8")), "Database budget_curve does not match artifact"
        assert sqlite_payload["payloads"]["pattern_vs_rate"] == json.loads((first_pay_root / "pattern_vs_rate.json").read_text(encoding="utf-8")), "Database pattern_vs_rate does not match artifact"
        assert sqlite_payload["payloads"]["reliability"] == json.loads((first_pay_root / "reliability.json").read_text(encoding="utf-8")), "Database reliability does not match artifact"
        assert sqlite_payload["payloads"]["decision_loss"] == json.loads((first_pay_root / "decision_loss.json").read_text(encoding="utf-8")), "Database decision_loss does not match artifact"

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
            "condition_count": len(first_conditions),
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
