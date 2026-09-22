"""Independent CLI, artifact, storage, and 4-payload verification for Gate 3 stress engine candidate."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
from uuid import uuid4

import psycopg

from shiftguard.experiments.ids import stable_hash


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
REQUIRED_COST_GRID = (
    (1.0, 1.0),
    (1.0, 4.0),
    (1.0, 9.0),
    (4.0, 1.0),
    (9.0, 1.0),
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

    valid_condition_ids: dict[str, dict[str, object]] = {}
    for k, c in conditions_data.items():
        cid = c.get("condition_id")
        if not cid or not isinstance(cid, str):
            raise AssertionError(f"Condition {k} has missing or non-string condition_id: {cid}")
        valid_condition_ids[cid] = c

    expected_scenarios = {f"{p}__{s}" for p in REQUIRED_PREDICTORS for s in REQUIRED_SCENARIOS}

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
                    if c.get("status") == "failed":
                        if c.get("metrics") is not None:
                            raise AssertionError(f"Failed condition {cond_key} must have null metrics, got: {c.get('metrics')}")
                    elif c.get("status") == "scored":
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
    if set(scenarios.keys()) != expected_scenarios:
        raise AssertionError(f"budget_curve scenarios mismatch: expected {sorted(expected_scenarios)}, got {sorted(scenarios.keys())}")
    for p in REQUIRED_PREDICTORS:
        for s in REQUIRED_SCENARIOS:
            ps_key = f"{p}__{s}"
            if ps_key not in scenarios:
                raise AssertionError(f"Missing scenario in budget_curve: {ps_key}")
            for m in REQUIRED_METHODS:
                if m not in scenarios[ps_key]:
                    raise AssertionError(f"Missing method {m} in budget_curve for {ps_key}")
                points = scenarios[ps_key][m]
                if not points or len(points) != len(REQUIRED_BUDGETS):
                    raise AssertionError(f"Expected {len(REQUIRED_BUDGETS)} points in budget_curve for {ps_key}/{m}, got {len(points)}")
                point_budgets = tuple(pt.get("budget") for pt in points)
                if point_budgets != REQUIRED_BUDGETS:
                    raise AssertionError(f"Expected budgets {REQUIRED_BUDGETS} in budget_curve for {ps_key}/{m}, got {point_budgets}")
                for pt in points:
                    cid = pt.get("condition_id")
                    if not cid or cid not in valid_condition_ids:
                        raise AssertionError(f"Point in budget_curve {ps_key}/{m} has nonexistent condition_id: {cid}")
                    b = pt.get("budget")
                    c_ref = valid_condition_ids[cid]
                    if (
                        c_ref.get("predictor") != p
                        or c_ref.get("scenario") != s
                        or c_ref.get("budget") != b
                        or c_ref.get("requested_method") != m
                    ):
                        raise AssertionError(
                            f"Point in budget_curve {ps_key}/{m} refers to mismatched condition: {cid} "
                            f"(expected predictor={p}, scenario={s}, budget={b}, method={m}; "
                            f"got predictor={c_ref.get('predictor')}, scenario={c_ref.get('scenario')}, "
                            f"budget={c_ref.get('budget')}, method={c_ref.get('requested_method')})"
                        )

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
    if set(comparisons.keys()) != set(REQUIRED_PREDICTORS):
        raise AssertionError(f"pattern_vs_rate comparisons predictors mismatch: expected {sorted(REQUIRED_PREDICTORS)}, got {sorted(comparisons.keys())}")
    for p in REQUIRED_PREDICTORS:
        if p not in comparisons:
            raise AssertionError(f"Missing predictor {p} in pattern_vs_rate comparisons")
        p_comp = comparisons[p]
        if p_comp.get("block_scenario") != "history_block_0_50" or p_comp.get("cellwise_scenario") != "mcar_matched_history":
            raise AssertionError(f"pattern_vs_rate comparison {p} has invalid scenario pair")
        if p_comp.get("budget") != 50:
            raise AssertionError(f"pattern_vs_rate comparison {p} has budget {p_comp.get('budget')} != 50")
        methods = p_comp.get("methods", {})
        if set(methods.keys()) != set(REQUIRED_METHODS):
            raise AssertionError(f"Missing methods in pattern_vs_rate comparisons for {p}: expected {sorted(REQUIRED_METHODS)}, got {sorted(methods.keys())}")
        for m in REQUIRED_METHODS:
            m_comp = methods[m]
            if "available" not in m_comp:
                raise AssertionError(f"Missing 'available' key in comparison for {p}/{m}")
            bcid = m_comp.get("block_condition_id")
            ccid = m_comp.get("cellwise_condition_id")
            if not bcid or bcid not in valid_condition_ids:
                raise AssertionError(f"Missing or nonexistent block_condition_id in pattern_vs_rate {p}/{m}: {bcid}")
            if not ccid or ccid not in valid_condition_ids:
                raise AssertionError(f"Missing or nonexistent cellwise_condition_id in pattern_vs_rate {p}/{m}: {ccid}")
            bc_ref = valid_condition_ids[bcid]
            cc_ref = valid_condition_ids[ccid]
            if (
                bc_ref.get("predictor") != p
                or bc_ref.get("scenario") != "history_block_0_50"
                or bc_ref.get("budget") != 50
                or bc_ref.get("requested_method") != m
            ):
                raise AssertionError(f"pattern_vs_rate {p}/{m} block condition mismatch: {bcid}")
            if (
                cc_ref.get("predictor") != p
                or cc_ref.get("scenario") != "mcar_matched_history"
                or cc_ref.get("budget") != 50
                or cc_ref.get("requested_method") != m
            ):
                raise AssertionError(f"pattern_vs_rate {p}/{m} cellwise condition mismatch: {ccid}")
            if "comparison_qualified" not in m_comp:
                raise AssertionError(f"Missing comparison_qualified in comparison for {p}/{m}")
            if m_comp["available"] is True:
                if m_comp.get("delta_brier") is None or not math.isfinite(float(m_comp["delta_brier"])):
                    raise AssertionError(f"Available comparison {p}/{m} missing finite delta_brier")
                b_metrics = bc_ref.get("metrics")
                c_metrics = cc_ref.get("metrics")
                if not b_metrics or not c_metrics:
                    raise AssertionError(f"Available comparison {p}/{m} condition metrics missing")
                b_brier = float(b_metrics["brier_score"])
                c_brier = float(c_metrics["brier_score"])
                expected_delta = b_brier - c_brier
                reported_delta = float(m_comp["delta_brier"])
                if not math.isclose(reported_delta, expected_delta, abs_tol=1e-6):
                    raise AssertionError(
                        f"Delta Brier mismatch for {p}/{m}: reported {reported_delta}, "
                        f"expected {expected_delta} = ({b_brier} - {c_brier})"
                    )

    # 3. reliability
    rel_file = payload_root / "reliability.json"
    if not rel_file.is_file():
        raise AssertionError("Artifact reliability.json is missing")
    rel_data = json.loads(rel_file.read_text(encoding="utf-8"))
    rel_scenarios = rel_data.get("scenarios", {})
    if not rel_scenarios:
        raise AssertionError("reliability.json has empty scenarios")
    if set(rel_scenarios.keys()) != expected_scenarios:
        raise AssertionError(f"reliability.json scenarios mismatch: expected {sorted(expected_scenarios)}, got {sorted(rel_scenarios.keys())}")
    for p in REQUIRED_PREDICTORS:
        for s in REQUIRED_SCENARIOS:
            ps_key = f"{p}__{s}"
            if ps_key not in rel_scenarios:
                raise AssertionError(f"Missing scenario in reliability.json: {ps_key}")
            methods_dict = rel_scenarios[ps_key]
            if set(methods_dict.keys()) != set(REQUIRED_METHODS):
                raise AssertionError(f"reliability.json {ps_key} missing methods: expected {sorted(REQUIRED_METHODS)}, got {sorted(methods_dict.keys())}")
            for m in REQUIRED_METHODS:
                m_data = methods_dict[m]
                cid = m_data.get("condition_id")
                if not cid or cid not in valid_condition_ids:
                    raise AssertionError(f"Reliability entry {ps_key}/{m} has nonexistent condition_id: {cid}")
                c_ref = valid_condition_ids[cid]
                if (
                    c_ref.get("predictor") != p
                    or c_ref.get("scenario") != s
                    or c_ref.get("requested_method") != m
                    or c_ref.get("budget") != 50
                ):
                    raise AssertionError(f"Reliability entry {ps_key}/{m} refers to mismatched condition: {cid}")
                bins = m_data.get("reliability_bins")
                if not bins or not isinstance(bins, list) or len(bins) == 0:
                    raise AssertionError(f"Reliability entry {ps_key}/{m} missing or empty reliability_bins")
                total_samples = sum(b.get("count", 0) for b in bins)
                if total_samples != EXPECTED_EVAL_ROWS:
                    raise AssertionError(f"Reliability diagram in {ps_key}/{m} has total count {total_samples} != {EXPECTED_EVAL_ROWS}")
                for b_dict in bins:
                    for k in ("lower", "upper", "count", "mean_probability", "positive_fraction"):
                        if k not in b_dict:
                            raise AssertionError(f"Reliability bin in {ps_key}/{m} missing required key: {k}")
                        val = b_dict[k]
                        if k == "count":
                            if not isinstance(val, int) or val < 0:
                                raise AssertionError(f"Reliability bin in {ps_key}/{m} invalid count: {val}")
                        elif k in ("lower", "upper"):
                            if not (isinstance(val, (int, float)) and math.isfinite(val) and 0.0 <= val <= 1.0):
                                raise AssertionError(f"Reliability bin in {ps_key}/{m} invalid bounds: {val}")
                        else:
                            if val is not None:
                                if not (isinstance(val, (int, float)) and math.isfinite(val) and 0.0 <= val <= 1.0):
                                    raise AssertionError(f"Reliability bin in {ps_key}/{m} has out-of-bounds {k}: {val}")

    # 4. decision_loss
    dl_file = payload_root / "decision_loss.json"
    if not dl_file.is_file():
        raise AssertionError("Artifact decision_loss.json is missing")
    dl_data = json.loads(dl_file.read_text(encoding="utf-8"))
    dl_scenarios = dl_data.get("scenarios", {})
    if not dl_scenarios:
        raise AssertionError("decision_loss.json has empty scenarios")
    if set(dl_scenarios.keys()) != expected_scenarios:
        raise AssertionError(f"decision_loss.json scenarios mismatch: expected {sorted(expected_scenarios)}, got {sorted(dl_scenarios.keys())}")
    for p in REQUIRED_PREDICTORS:
        for s in REQUIRED_SCENARIOS:
            ps_key = f"{p}__{s}"
            if ps_key not in dl_scenarios:
                raise AssertionError(f"Missing scenario in decision_loss.json: {ps_key}")
            methods_dict = dl_scenarios[ps_key]
            if set(methods_dict.keys()) != set(REQUIRED_METHODS):
                raise AssertionError(f"decision_loss.json {ps_key} missing methods: expected {sorted(REQUIRED_METHODS)}, got {sorted(methods_dict.keys())}")
            for m in REQUIRED_METHODS:
                m_data = methods_dict[m]
                cid = m_data.get("condition_id")
                if not cid or cid not in valid_condition_ids:
                    raise AssertionError(f"Decision loss entry {ps_key}/{m} has nonexistent condition_id: {cid}")
                c_ref = valid_condition_ids[cid]
                if (
                    c_ref.get("predictor") != p
                    or c_ref.get("scenario") != s
                    or c_ref.get("requested_method") != m
                    or c_ref.get("budget") != 50
                ):
                    raise AssertionError(
                        f"Decision loss entry {ps_key}/{m} refers to mismatched condition: {cid} "
                        f"(expected predictor={p}, scenario={s}, budget=50, method={m}; "
                        f"got predictor={c_ref.get('predictor')}, scenario={c_ref.get('scenario')}, "
                        f"budget={c_ref.get('budget')}, method={c_ref.get('requested_method')})"
                    )
                c_metrics = c_ref.get("metrics")
                if not c_metrics or "decision_loss" not in c_metrics:
                    raise AssertionError(f"Condition {cid} referenced by decision loss {ps_key}/{m} missing decision_loss metrics")
                cond_cost_losses = c_metrics["decision_loss"]
                if not isinstance(cond_cost_losses, list) or len(cond_cost_losses) != len(REQUIRED_COST_GRID):
                    raise AssertionError(f"Condition {cid} decision_loss metrics length != {len(REQUIRED_COST_GRID)}")
                cost_losses = m_data.get("cost_grid_losses")
                if not cost_losses or not isinstance(cost_losses, list):
                    raise AssertionError(f"Decision loss entry {ps_key}/{m} has empty or non-list cost_grid_losses")
                if len(cost_losses) != len(REQUIRED_COST_GRID):
                    raise AssertionError(f"Decision loss entry {ps_key}/{m} cost_grid_losses count {len(cost_losses)} != {len(REQUIRED_COST_GRID)}")
                actual_cost_pairs = tuple((float(row.get("fp_cost", 0.0)), float(row.get("fn_cost", 0.0))) for row in cost_losses)
                if actual_cost_pairs != REQUIRED_COST_GRID:
                    raise AssertionError(f"Decision loss entry {ps_key}/{m} cost pairs {actual_cost_pairs} != expected {REQUIRED_COST_GRID}")
                for idx, row in enumerate(cost_losses):
                    cond_row = cond_cost_losses[idx]
                    for k in ("fp_cost", "fn_cost", "threshold", "loss", "n_samples", "tp_count", "fp_count", "tn_count", "fn_count"):
                        if k not in row:
                            raise AssertionError(f"Decision loss row in {ps_key}/{m} missing required key: {k}")
                        if k not in cond_row:
                            raise AssertionError(f"Condition {cid} decision_loss row missing required key: {k}")
                        val = row[k]
                        cond_val = cond_row[k]
                        if k in ("fp_cost", "fn_cost", "threshold", "loss"):
                            if not math.isclose(float(val), float(cond_val), abs_tol=1e-6):
                                raise AssertionError(
                                    f"Decision loss row in {ps_key}/{m} key {k} value {val} does not agree with "
                                    f"referenced condition {cid} metric value {cond_val}"
                                )
                        else:
                            if val != cond_val:
                                raise AssertionError(
                                    f"Decision loss row in {ps_key}/{m} key {k} value {val} does not agree with "
                                    f"referenced condition {cid} metric value {cond_val}"
                                )
                    if row["n_samples"] != EXPECTED_EVAL_ROWS:
                        raise AssertionError(f"Decision loss row in {ps_key}/{m} has n_samples {row['n_samples']} != {EXPECTED_EVAL_ROWS}")
                    tp, fp, tn, fn = row["tp_count"], row["fp_count"], row["tn_count"], row["fn_count"]
                    if not all(isinstance(c, int) and c >= 0 for c in (tp, fp, tn, fn)):
                        raise AssertionError(f"Decision loss row in {ps_key}/{m} has non-integer or negative confusion counts")
                    if tp + fp + tn + fn != EXPECTED_EVAL_ROWS:
                        raise AssertionError(f"Decision loss row in {ps_key}/{m} confusion counts sum to {tp + fp + tn + fn} != {EXPECTED_EVAL_ROWS}")
                    loss = row["loss"]
                    if not (math.isfinite(loss) and loss >= 0.0):
                        raise AssertionError(f"Decision loss row in {ps_key}/{m} has invalid loss: {loss}")
                    thresh = row["threshold"]
                    if not (math.isfinite(thresh) and 0.0 <= thresh <= 1.0):
                        raise AssertionError(f"Decision loss row in {ps_key}/{m} has invalid threshold: {thresh}")
                    expected_thresh = row["fp_cost"] / (row["fp_cost"] + row["fn_cost"])
                    if not math.isclose(thresh, expected_thresh, abs_tol=1e-6):
                        raise AssertionError(
                            f"Decision loss row in {ps_key}/{m} threshold {thresh} != "
                            f"expected FP/(FP+FN) {expected_thresh} for costs ({row['fp_cost']}, {row['fn_cost']})"
                        )
                    expected_loss = (row["fp_cost"] * fp + row["fn_cost"] * fn) / EXPECTED_EVAL_ROWS
                    if not math.isclose(loss, expected_loss, abs_tol=1e-6):
                        raise AssertionError(f"Decision loss row in {ps_key}/{m} loss mismatch: reported {loss}, calculated {expected_loss}")

    return {
        "condition_count": len(conditions_data),
        "scientific_matrix_verified": True,
        "evaluator_row_count_verified": True,
        "matching_strategy_verified": True,
    }


REQUIRED_MANIFEST_KEYS = {
    "config",
    "seeds",
    "masks",
    "acquisition",
    "conditions",
    "comparisons",
    "budget_curve",
    "pattern_vs_rate",
    "reliability",
    "decision_loss",
    "logical_content",
}


def validate_manifest_content_hashes(
    content_hashes: dict[str, str],
    artifact_root: Path,
    payload_root: Path,
) -> None:
    """Verify exact match against REQUIRED_MANIFEST_KEYS and byte digests of all artifacts."""
    if set(content_hashes.keys()) != REQUIRED_MANIFEST_KEYS:
        diff = set(content_hashes.keys()) ^ REQUIRED_MANIFEST_KEYS
        raise AssertionError(f"Exact manifest mismatch: {diff}")

    for key, digest in content_hashes.items():
        if key == "logical_content":
            continue
        if key in REQUIRED_PAYLOADS:
            target_file = payload_root / f"{key}.json"
        else:
            target_file = artifact_root / f"{key}.json"
        if not target_file.is_file():
            raise AssertionError(f"Artifact file missing: {target_file}")
        actual_hash = hashlib.sha256(target_file.read_bytes()).hexdigest()
        if actual_hash != digest:
            raise AssertionError(f"Artifact hash mismatch for {key}: expected {digest}, got {actual_hash}")


def validate_condition_ids_preimages(conditions_data: dict[str, dict[str, object]]) -> None:
    """Independently recompute and verify condition IDs from their exact preimages."""
    for cond_key, cond in conditions_data.items():
        preimage = {k: v for k, v in cond.items() if k != "condition_id"}
        expected_cid = stable_hash(preimage)[:24]
        if cond.get("condition_id") != expected_cid:
            raise AssertionError(
                f"Condition {cond_key} ID mismatch: expected {expected_cid}, got {cond.get('condition_id')}"
            )


def validate_database_projections(
    payload: dict[str, object],
    artifact_root: Path,
    payload_root: Path,
) -> None:
    """Compare all 10 stored database projections with on-disk artifacts."""
    projections = {
        "config": (artifact_root / "config.json", payload.get("config")),
        "seeds": (artifact_root / "seeds.json", payload.get("seeds")),
        "masks": (artifact_root / "masks.json", payload.get("masks")),
        "acquisition": (artifact_root / "acquisition.json", payload.get("acquisition")),
        "conditions": (artifact_root / "conditions.json", payload.get("conditions")),
        "comparisons": (artifact_root / "comparisons.json", payload.get("comparisons")),
        "budget_curve": (payload_root / "budget_curve.json", payload.get("payloads", {}).get("budget_curve")),
        "pattern_vs_rate": (payload_root / "pattern_vs_rate.json", payload.get("payloads", {}).get("pattern_vs_rate")),
        "reliability": (payload_root / "reliability.json", payload.get("payloads", {}).get("reliability")),
        "decision_loss": (payload_root / "decision_loss.json", payload.get("payloads", {}).get("decision_loss")),
    }
    for proj_name, (proj_file, proj_db) in projections.items():
        if not proj_file.is_file():
            raise AssertionError(f"Projection file missing: {proj_file}")
        file_content = json.loads(proj_file.read_text(encoding="utf-8"))
        if file_content != proj_db:
            raise AssertionError(f"Database projection {proj_name} does not match saved artifact")


def validate_logical_content_and_experiment_id(
    payload: dict[str, object],
    content_hashes: dict[str, str],
    experiment_id: str,
) -> None:
    """Recompute logical content digest and experiment ID from database payload."""
    recomputed_logical = stable_hash(payload)
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
    canonical_verification = output_dir / "verification.json"
    if canonical_verification.exists():
        canonical_verification.unlink()

    attempts_dir = output_dir / "attempts"
    attempts_dir.mkdir(parents=True, exist_ok=True)
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
        expected_commit = get_expected_commit()
        _write_current_attempt({
            "candidate": expected_commit,
            "attempt_id": attempt_id,
            "status": "IN_PROGRESS",
            "started_at": datetime.now(timezone.utc).isoformat(),
        })
        if "SHIFTGUARD_TEST_POSTGRES_URL" not in os.environ:
            raise RuntimeError("SHIFTGUARD_TEST_POSTGRES_URL is required for Gate 3 reproduction verification")
        postgres_url = os.environ["SHIFTGUARD_TEST_POSTGRES_URL"]
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

                # 1. Exact manifest validation (A04) & 2. Verify byte hashes of all generated artifacts
                validate_manifest_content_hashes(content_hashes, artifact_root, payload_root)

                # 3. Read and validate conditions.json and scientific payloads
                conditions_file = artifact_root / "conditions.json"
                assert conditions_file.is_file(), "conditions.json missing"
                conditions_data = json.loads(conditions_file.read_text(encoding="utf-8"))
                validate_scientific_payloads(artifact_root, payload_root, conditions_data)

                # 4. Recompute condition IDs independently from preimages (A04)
                validate_condition_ids_preimages(conditions_data)

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

            # 5. Compare ALL database projections with saved artifacts (A04)
            first_art_root = APP / "var/artifacts" / first["experiment_id"]
            first_pay_root = first_art_root / "payloads"
            validate_database_projections(sqlite_payload, first_art_root, first_pay_root)

            # 6. Recompute logical content digest and experiment ID independently (A04)
            validate_logical_content_and_experiment_id(sqlite_payload, first["content_hashes"], first["experiment_id"])

            audits = {row[0]: json.loads(row[1]) for row in sqlite_audits + postgres_audits}
            assert all(execution in audits for execution in execution_ids), "Missing audits for executions"

            provenance_summary = validate_execution_provenance(execution_ids, audits, expected_commit)
            provenance_summary["verifier_sha256"] = verifier_sha256

            first_conditions = sqlite_payload["conditions"]
            summary = {
                "status": "passed",
                "gate": 3,
                "attempt_id": attempt_id,
                "experiment_id": first["experiment_id"],
                "execution_ids": execution_ids,
                "identical_artifact_hashes": first["content_hashes"],
                "payload_keys": list(REQUIRED_PAYLOADS),
                "condition_count": len(first_conditions),
                "sqlite_and_postgres_payloads_equal": True,
                "execution_audits": {key: audits[key] for key in execution_ids},
                "verified_provenance": provenance_summary,
            }

            # Write outputs to both the immutable attempt directory and canonical output dir
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

            print(json.dumps({
                "status": "passed",
                "gate": 3,
                "attempt_id": attempt_id,
                "experiment_id": first["experiment_id"],
                "executions": execution_ids,
                "verified_commit": expected_commit,
            }))

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
