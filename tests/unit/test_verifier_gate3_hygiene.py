from __future__ import annotations

import json
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


def _build_valid_test_payloads(tmp_path: Path) -> tuple[Path, Path, dict[str, dict]]:
    import hashlib
    artifact_root = tmp_path / "artifacts"
    payload_root = artifact_root / "payloads"
    payload_root.mkdir(parents=True, exist_ok=True)

    conditions = {}
    for p in vg3.REQUIRED_PREDICTORS:
        for s in vg3.REQUIRED_SCENARIOS:
            for b in vg3.REQUIRED_BUDGETS:
                for m in vg3.REQUIRED_METHODS:
                    key = f"{p}__{s}__b{b}__{m}"
                    cid = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
                    conditions[key] = {
                        "name": key,
                        "condition_id": cid,
                        "predictor": p,
                        "scenario": s,
                        "budget": b,
                        "requested_method": m,
                        "resolved_method": m,
                        "status": "scored",
                        "metrics": {
                            "brier_score": 0.12,
                            "log_loss": 0.35,
                            "ece": 0.04,
                            "roc_auc": 0.88,
                            "average_precision": 0.65,
                            "decision_loss": [{"cost": [1.0, 1.0], "threshold": 0.5, "loss": 0.1}],
                        },
                    }

    # budget_curve.json
    bc_scenarios = {}
    for p in vg3.REQUIRED_PREDICTORS:
        for s in vg3.REQUIRED_SCENARIOS:
            ps_key = f"{p}__{s}"
            bc_scenarios[ps_key] = {
                m: [
                    {
                        "budget": b,
                        "status": "scored",
                        "condition_id": conditions[f"{p}__{s}__b{b}__{m}"]["condition_id"],
                    }
                    for b in vg3.REQUIRED_BUDGETS
                ]
                for m in vg3.REQUIRED_METHODS
            }
    (payload_root / "budget_curve.json").write_text(json.dumps({"scenarios": bc_scenarios}), encoding="utf-8")

    # pattern_vs_rate.json
    pvr_comparisons = {}
    for p in vg3.REQUIRED_PREDICTORS:
        methods_comp = {}
        for m in vg3.REQUIRED_METHODS:
            b_cid = conditions[f"{p}__history_block_0_50__b50__{m}"]["condition_id"]
            c_cid = conditions[f"{p}__mcar_matched_history__b50__{m}"]["condition_id"]
            methods_comp[m] = {
                "available": True,
                "comparison_qualified": True,
                "matching_status": "within_tolerance",
                "tolerance": 0.01,
                "residual_mismatch": 0.002,
                "block_condition_id": b_cid,
                "cellwise_condition_id": c_cid,
                "delta_brier": 0.005,
            }
        pvr_comparisons[p] = {"methods": methods_comp}
    pvr_data = {
        "matching_report": {
            "matching_strategy": "bernoulli_matched_rate",
            "matching_status": "within_tolerance",
            "comparison_qualified": True,
        },
        "comparisons": pvr_comparisons,
    }
    (payload_root / "pattern_vs_rate.json").write_text(json.dumps(pvr_data), encoding="utf-8")

    # reliability.json
    rel_scenarios = {}
    for p in vg3.REQUIRED_PREDICTORS:
        for s in vg3.REQUIRED_SCENARIOS:
            ps_key = f"{p}__{s}"
            rel_scenarios[ps_key] = {
                "raw": {
                    "condition_id": conditions[f"{p}__{s}__b0__raw"]["condition_id"],
                    "reliability_bins": [{"bin": 0, "count": 8238, "mean_predicted": 0.1, "mean_true": 0.1}],
                }
            }
    (payload_root / "reliability.json").write_text(json.dumps({"scenarios": rel_scenarios}), encoding="utf-8")

    # decision_loss.json
    dl_scenarios = {}
    for p in vg3.REQUIRED_PREDICTORS:
        for s in vg3.REQUIRED_SCENARIOS:
            ps_key = f"{p}__{s}"
            dl_scenarios[ps_key] = {
                "raw": {
                    "condition_id": conditions[f"{p}__{s}__b0__raw"]["condition_id"],
                    "cost_grid_losses": [{"cost": [1.0, 1.0], "threshold": 0.5, "loss": 0.1}],
                }
            }
    (payload_root / "decision_loss.json").write_text(json.dumps({"scenarios": dl_scenarios}), encoding="utf-8")

    return artifact_root, payload_root, conditions


def test_validate_scientific_payloads_valid(tmp_path):
    art_root, pay_root, conditions = _build_valid_test_payloads(tmp_path)
    res = vg3.validate_scientific_payloads(art_root, pay_root, conditions)
    assert res["condition_count"] == 400
    assert res["scientific_matrix_verified"] is True
    assert res["evaluator_row_count_verified"] is True


def test_validate_scientific_payloads_rejects_empty_or_wrong_count(tmp_path):
    art_root, pay_root, conditions = _build_valid_test_payloads(tmp_path)

    # Empty conditions
    with pytest.raises(AssertionError, match="must not be empty"):
        vg3.validate_scientific_payloads(art_root, pay_root, {})

    # 399 conditions
    del conditions[next(iter(conditions))]
    with pytest.raises(AssertionError, match="Expected 400 conditions"):
        vg3.validate_scientific_payloads(art_root, pay_root, conditions)


def test_validate_scientific_payloads_rejects_dishonest_matching_strategy(tmp_path):
    art_root, pay_root, conditions = _build_valid_test_payloads(tmp_path)

    # Change matching strategy to exact_realized_rate
    pvr_path = pay_root / "pattern_vs_rate.json"
    data = json.loads(pvr_path.read_text(encoding="utf-8"))
    data["matching_report"]["matching_strategy"] = "exact_realized_rate"
    pvr_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(AssertionError, match="matching_strategy must be 'bernoulli_matched_rate'"):
        vg3.validate_scientific_payloads(art_root, pay_root, conditions)


def test_validate_scientific_payloads_rejects_wrong_reliability_row_count(tmp_path):
    art_root, pay_root, conditions = _build_valid_test_payloads(tmp_path)

    rel_path = pay_root / "reliability.json"
    data = json.loads(rel_path.read_text(encoding="utf-8"))
    # Corrupt sample count to 8000
    first_scen = next(iter(data["scenarios"].values()))
    first_scen["raw"]["reliability_bins"][0]["count"] = 8000
    rel_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(AssertionError, match="total count 8000 != 8238"):
        vg3.validate_scientific_payloads(art_root, pay_root, conditions)


def test_validate_scientific_payloads_rejects_out_of_bounds_metrics(tmp_path):
    art_root, pay_root, conditions = _build_valid_test_payloads(tmp_path)

    first_cond = next(iter(conditions.values()))
    first_cond["metrics"]["brier_score"] = 1.25

    with pytest.raises(AssertionError, match="brier_score out of bounds"):
        vg3.validate_scientific_payloads(art_root, pay_root, conditions)


def test_validate_scientific_payloads_rejects_nonexistent_condition_reference(tmp_path):
    art_root, pay_root, conditions = _build_valid_test_payloads(tmp_path)

    # Point in budget_curve references a nonexistent condition_id
    bc_path = pay_root / "budget_curve.json"
    data = json.loads(bc_path.read_text(encoding="utf-8"))
    first_scen = next(iter(data["scenarios"].values()))
    first_scen["raw"][0]["condition_id"] = "nonexistent_condition_id"
    bc_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(AssertionError, match="nonexistent condition_id"):
        vg3.validate_scientific_payloads(art_root, pay_root, conditions)


def test_validate_scientific_payloads_rejects_budget999(tmp_path):
    art_root, pay_root, conditions = _build_valid_test_payloads(tmp_path)

    # Point in budget_curve has budget 999
    bc_path = pay_root / "budget_curve.json"
    data = json.loads(bc_path.read_text(encoding="utf-8"))
    first_scen = next(iter(data["scenarios"].values()))
    first_scen["raw"][0]["budget"] = 999
    bc_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(AssertionError, match="unsupported budget: 999"):
        vg3.validate_scientific_payloads(art_root, pay_root, conditions)


def test_validate_scientific_payloads_rejects_invented_or_empty_scenarios(tmp_path):
    art_root, pay_root, conditions = _build_valid_test_payloads(tmp_path)

    # Invented scenario in reliability.json
    rel_path = pay_root / "reliability.json"
    data = json.loads(rel_path.read_text(encoding="utf-8"))
    data["scenarios"]["invented_scenario"] = {"raw": {}}
    rel_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(AssertionError, match="invented scenarios"):
        vg3.validate_scientific_payloads(art_root, pay_root, conditions)


def test_validate_scientific_payloads_rejects_failed_condition_with_nonnull_metrics(tmp_path):
    art_root, pay_root, conditions = _build_valid_test_payloads(tmp_path)

    first_cond = next(iter(conditions.values()))
    first_cond["status"] = "failed"
    # Metrics remain populated (non-null), violating failed contract
    assert first_cond.get("metrics") is not None

    with pytest.raises(AssertionError, match="must have null metrics"):
        vg3.validate_scientific_payloads(art_root, pay_root, conditions)


def test_validate_scientific_payloads_rejects_unsupported_evaluator_rows(tmp_path):
    art_root, pay_root, conditions = _build_valid_test_payloads(tmp_path)

    # Corrupt reliability bins to have 0 bins (empty)
    rel_path = pay_root / "reliability.json"
    data = json.loads(rel_path.read_text(encoding="utf-8"))
    first_scen = next(iter(data["scenarios"].values()))
    first_scen["raw"]["reliability_bins"] = []
    rel_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(AssertionError, match="total count 0 != 8238"):
        vg3.validate_scientific_payloads(art_root, pay_root, conditions)
