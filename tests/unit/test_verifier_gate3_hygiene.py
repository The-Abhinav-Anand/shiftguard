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
                    brier = 0.125 if s == "history_block_0_50" else 0.120
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
                            "brier_score": brier,
                            "log_loss": 0.35,
                            "ece": 0.04,
                            "roc_auc": 0.88,
                            "average_precision": 0.65,
                            "decision_loss": [
                                {
                                    "fp_cost": fp_c,
                                    "fn_cost": fn_c,
                                    "threshold": fp_c / (fp_c + fn_c),
                                    "fp_count": 200,
                                    "fn_count": 238,
                                    "tp_count": 800,
                                    "tn_count": 7000,
                                    "n_samples": 8238,
                                    "loss": (fp_c * 200 + fn_c * 238) / 8238,
                                }
                                for fp_c, fn_c in [(1.0, 1.0), (1.0, 4.0), (1.0, 9.0), (4.0, 1.0), (9.0, 1.0)]
                            ],
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
                "block_brier": 0.125,
                "cellwise_brier": 0.120,
                "delta_brier": 0.005,
            }
        pvr_comparisons[p] = {
            "block_scenario": "history_block_0_50",
            "cellwise_scenario": "mcar_matched_history",
            "budget": 50,
            "methods": methods_comp,
        }
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
                m: {
                    "condition_id": conditions[f"{p}__{s}__b50__{m}"]["condition_id"],
                    "reliability_bins": [
                        {
                            "lower": 0.0,
                            "upper": 1.0,
                            "count": 8238,
                            "mean_probability": 0.1,
                            "positive_fraction": 0.1,
                        }
                    ],
                }
                for m in vg3.REQUIRED_METHODS
            }
    (payload_root / "reliability.json").write_text(json.dumps({"scenarios": rel_scenarios}), encoding="utf-8")

    # decision_loss.json
    dl_scenarios = {}
    for p in vg3.REQUIRED_PREDICTORS:
        for s in vg3.REQUIRED_SCENARIOS:
            ps_key = f"{p}__{s}"
            dl_scenarios[ps_key] = {
                m: {
                    "condition_id": conditions[f"{p}__{s}__b50__{m}"]["condition_id"],
                    "cost_grid_losses": [
                        {
                            "fp_cost": fp_c,
                            "fn_cost": fn_c,
                            "threshold": fp_c / (fp_c + fn_c),
                            "fp_count": 200,
                            "fn_count": 238,
                            "tp_count": 800,
                            "tn_count": 7000,
                            "n_samples": 8238,
                            "loss": (fp_c * 200 + fn_c * 238) / 8238,
                        }
                        for fp_c, fn_c in [(1.0, 1.0), (1.0, 4.0), (1.0, 9.0), (4.0, 1.0), (9.0, 1.0)]
                    ],
                }
                for m in vg3.REQUIRED_METHODS
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

    bc_path = pay_root / "budget_curve.json"
    data = json.loads(bc_path.read_text(encoding="utf-8"))
    first_scen = next(iter(data["scenarios"].values()))
    first_scen["raw"][0]["condition_id"] = "nonexistent_condition_id"
    bc_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(AssertionError, match="nonexistent condition_id"):
        vg3.validate_scientific_payloads(art_root, pay_root, conditions)


def test_validate_scientific_payloads_rejects_duplicated_or_wrong_budgets(tmp_path):
    art_root, pay_root, conditions = _build_valid_test_payloads(tmp_path)

    bc_path = pay_root / "budget_curve.json"
    data = json.loads(bc_path.read_text(encoding="utf-8"))
    first_scen = next(iter(data["scenarios"].values()))
    # Duplicate budget 0 instead of budget 25
    first_scen["raw"][1]["budget"] = 0
    bc_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(AssertionError, match="Expected budgets"):
        vg3.validate_scientific_payloads(art_root, pay_root, conditions)


def test_validate_scientific_payloads_rejects_mismatched_condition_reference(tmp_path):
    art_root, pay_root, conditions = _build_valid_test_payloads(tmp_path)

    bc_path = pay_root / "budget_curve.json"
    data = json.loads(bc_path.read_text(encoding="utf-8"))
    # Point in logistic_regression__baseline references a random_forest condition
    first_scen = next(iter(data["scenarios"].values()))
    first_scen["raw"][0]["condition_id"] = conditions["random_forest__baseline__b0__raw"]["condition_id"]
    bc_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(AssertionError, match="refers to mismatched condition"):
        vg3.validate_scientific_payloads(art_root, pay_root, conditions)


def test_validate_scientific_payloads_rejects_delta_brier_mismatch(tmp_path):
    art_root, pay_root, conditions = _build_valid_test_payloads(tmp_path)

    pvr_path = pay_root / "pattern_vs_rate.json"
    data = json.loads(pvr_path.read_text(encoding="utf-8"))
    # Corrupt reported delta_brier to 0.099 (true difference is 0.125 - 0.120 = 0.005)
    data["comparisons"]["logistic_regression"]["methods"]["raw"]["delta_brier"] = 0.099
    pvr_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(AssertionError, match="Delta Brier mismatch"):
        vg3.validate_scientific_payloads(art_root, pay_root, conditions)


def test_validate_scientific_payloads_rejects_decision_loss_confusion_sum_mismatch(tmp_path):
    art_root, pay_root, conditions = _build_valid_test_payloads(tmp_path)

    dl_path = pay_root / "decision_loss.json"
    data = json.loads(dl_path.read_text(encoding="utf-8"))
    first_scen = next(iter(data["scenarios"].values()))
    # Corrupt confusion counts in both payload and condition so agreement passes but sum != 8238 fails
    first_scen["raw"]["cost_grid_losses"][0]["fp_count"] = 500
    conditions["logistic_regression__baseline__b50__raw"]["metrics"]["decision_loss"][0]["fp_count"] = 500
    dl_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(AssertionError, match="confusion counts sum to"):
        vg3.validate_scientific_payloads(art_root, pay_root, conditions)


def test_validate_scientific_payloads_rejects_invented_or_empty_scenarios(tmp_path):
    art_root, pay_root, conditions = _build_valid_test_payloads(tmp_path)

    rel_path = pay_root / "reliability.json"
    data = json.loads(rel_path.read_text(encoding="utf-8"))
    data["scenarios"]["invented_scenario"] = {"raw": {}}
    rel_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(AssertionError, match="reliability.json scenarios mismatch"):
        vg3.validate_scientific_payloads(art_root, pay_root, conditions)


def test_validate_scientific_payloads_rejects_failed_condition_with_nonnull_metrics(tmp_path):
    art_root, pay_root, conditions = _build_valid_test_payloads(tmp_path)

    first_cond = next(iter(conditions.values()))
    first_cond["status"] = "failed"
    assert first_cond.get("metrics") is not None

    with pytest.raises(AssertionError, match="must have null metrics"):
        vg3.validate_scientific_payloads(art_root, pay_root, conditions)


def test_validate_scientific_payloads_rejects_unsupported_evaluator_rows(tmp_path):
    art_root, pay_root, conditions = _build_valid_test_payloads(tmp_path)

    rel_path = pay_root / "reliability.json"
    data = json.loads(rel_path.read_text(encoding="utf-8"))
    first_scen = next(iter(data["scenarios"].values()))
    first_scen["raw"]["reliability_bins"] = []
    rel_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(AssertionError, match="missing or empty reliability_bins"):
        vg3.validate_scientific_payloads(art_root, pay_root, conditions)


def test_validate_scientific_payloads_rejects_cost_grid_sequence_mismatch(tmp_path):
    art_root, pay_root, conditions = _build_valid_test_payloads(tmp_path)

    dl_path = pay_root / "decision_loss.json"
    data = json.loads(dl_path.read_text(encoding="utf-8"))
    first_scen = next(iter(data["scenarios"].values()))
    # Duplicate first cost pair (1.0, 1.0) into second row instead of (1.0, 4.0)
    first_scen["raw"]["cost_grid_losses"][1]["fp_cost"] = 1.0
    first_scen["raw"]["cost_grid_losses"][1]["fn_cost"] = 1.0
    dl_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(AssertionError, match="cost pairs .* != expected"):
        vg3.validate_scientific_payloads(art_root, pay_root, conditions)


def test_validate_scientific_payloads_rejects_threshold_formula_mismatch(tmp_path):
    art_root, pay_root, conditions = _build_valid_test_payloads(tmp_path)

    dl_path = pay_root / "decision_loss.json"
    data = json.loads(dl_path.read_text(encoding="utf-8"))
    first_scen = next(iter(data["scenarios"].values()))
    # Set symmetric-cost row (1.0, 1.0) threshold to 0.9 (expected is 0.5)
    first_scen["raw"]["cost_grid_losses"][0]["threshold"] = 0.9
    # Keep referenced condition in sync so agreement check passes and threshold formula fails
    conditions["logistic_regression__baseline__b50__raw"]["metrics"]["decision_loss"][0]["threshold"] = 0.9
    dl_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(AssertionError, match="expected FP/\\(FP\\+FN\\) 0.5"):
        vg3.validate_scientific_payloads(art_root, pay_root, conditions)


def test_validate_scientific_payloads_rejects_decision_loss_non_budget50_binding(tmp_path):
    art_root, pay_root, conditions = _build_valid_test_payloads(tmp_path)

    dl_path = pay_root / "decision_loss.json"
    data = json.loads(dl_path.read_text(encoding="utf-8"))
    first_scen = next(iter(data["scenarios"].values()))
    # Point raw decision_loss to b0 instead of b50
    first_scen["raw"]["condition_id"] = conditions["logistic_regression__baseline__b0__raw"]["condition_id"]
    dl_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(AssertionError, match="budget=50"):
        vg3.validate_scientific_payloads(art_root, pay_root, conditions)


def test_validate_scientific_payloads_rejects_decision_loss_copied_from_different_condition(tmp_path):
    art_root, pay_root, conditions = _build_valid_test_payloads(tmp_path)

    dl_path = pay_root / "decision_loss.json"
    data = json.loads(dl_path.read_text(encoding="utf-8"))
    first_scen = next(iter(data["scenarios"].values()))
    # Alter confusion counts so row is internally consistent but disagrees with referenced condition
    first_scen["raw"]["cost_grid_losses"][0]["tp_count"] = 750
    first_scen["raw"]["cost_grid_losses"][0]["tn_count"] = 7050
    first_scen["raw"]["cost_grid_losses"][0]["loss"] = (1.0 * 200 + 1.0 * 238) / 8238
    dl_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(AssertionError, match="does not agree with referenced condition"):
        vg3.validate_scientific_payloads(art_root, pay_root, conditions)


def test_gate3_current_attempt_pointer_records_failed_status_and_attempt_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("SHIFTGUARD_TEST_POSTGRES_URL", raising=False)
    monkeypatch.setenv("SHIFTGUARD_VERIFICATION_OUTPUT", str(tmp_path))

    with pytest.raises(RuntimeError, match="SHIFTGUARD_TEST_POSTGRES_URL is required"):
        vg3.main()

    pointer = tmp_path / "current_attempt.json"
    assert pointer.is_file(), "current_attempt.json must exist"
    pointer_data = json.loads(pointer.read_text(encoding="utf-8"))
    assert pointer_data["status"] == "FAILED"
    assert "SHIFTGUARD_TEST_POSTGRES_URL is required" in pointer_data["error"]
    assert "attempt_id" in pointer_data
    assert "failed_at" in pointer_data

    attempt_dir = tmp_path / "attempts" / pointer_data["attempt_id"]
    assert attempt_dir.is_dir(), f"Attempt directory {attempt_dir} must have been created"


def test_validate_manifest_content_hashes_exact_keys_and_digests(tmp_path):
    import hashlib
    art_root = tmp_path / "art"
    pay_root = art_root / "payloads"
    art_root.mkdir(parents=True, exist_ok=True)
    pay_root.mkdir(parents=True, exist_ok=True)

    # Build valid files
    content_hashes = {}
    for key in vg3.REQUIRED_MANIFEST_KEYS:
        if key == "logical_content":
            content_hashes[key] = "dummy_logical_hash"
            continue
        content = f'{{"key": "{key}"}}\n'.encode("utf-8")
        if key in vg3.REQUIRED_PAYLOADS:
            f = pay_root / f"{key}.json"
        else:
            f = art_root / f"{key}.json"
        f.write_bytes(content)
        content_hashes[key] = hashlib.sha256(content).hexdigest()

    # Valid manifest passes
    vg3.validate_manifest_content_hashes(content_hashes, art_root, pay_root)

    # Missing required key rejected
    bad_missing = dict(content_hashes)
    del bad_missing["acquisition"]
    with pytest.raises(AssertionError, match="Exact manifest mismatch"):
        vg3.validate_manifest_content_hashes(bad_missing, art_root, pay_root)

    # Extra unexpected key rejected
    bad_extra = dict(content_hashes)
    bad_extra["unexpected_extra"] = "some_hash"
    with pytest.raises(AssertionError, match="Exact manifest mismatch"):
        vg3.validate_manifest_content_hashes(bad_extra, art_root, pay_root)

    # Byte hash mismatch rejected
    bad_hash = dict(content_hashes)
    bad_hash["config"] = "0000000000000000000000000000000000000000000000000000000000000000"
    with pytest.raises(AssertionError, match="Artifact hash mismatch for config"):
        vg3.validate_manifest_content_hashes(bad_hash, art_root, pay_root)


def test_validate_condition_ids_preimages_recomputation(tmp_path):
    from shiftguard.experiments.ids import stable_hash

    # Valid condition
    c1 = {
        "name": "lr_baseline",
        "predictor": "logistic_regression",
        "scenario": "baseline",
        "budget": 50,
    }
    c1["condition_id"] = stable_hash(c1)[:24]
    conditions_data = {"c1": c1}

    # Should pass
    vg3.validate_condition_ids_preimages(conditions_data)

    # Tampered condition_id rejected
    c1_tampered = dict(c1)
    c1_tampered["condition_id"] = "bad_condition_id_123456"
    with pytest.raises(AssertionError, match="ID mismatch"):
        vg3.validate_condition_ids_preimages({"c1": c1_tampered})


def test_validate_database_projections_all_ten_tables(tmp_path):
    art_root = tmp_path / "art"
    pay_root = art_root / "payloads"
    art_root.mkdir(parents=True, exist_ok=True)
    pay_root.mkdir(parents=True, exist_ok=True)

    payload = {
        "config": {"setting": 1},
        "seeds": {"seed": 42},
        "masks": {"mask": "m1"},
        "acquisition": {"count": 50},
        "conditions": {"cond": "c1"},
        "comparisons": {"comp": "cmp1"},
        "payloads": {
            "budget_curve": {"curve": [1, 2]},
            "pattern_vs_rate": {"pvr": True},
            "reliability": {"rel": [0.1]},
            "decision_loss": {"loss": 0.05},
        },
    }

    # Write identical disk files
    (art_root / "config.json").write_text(json.dumps(payload["config"]), encoding="utf-8")
    (art_root / "seeds.json").write_text(json.dumps(payload["seeds"]), encoding="utf-8")
    (art_root / "masks.json").write_text(json.dumps(payload["masks"]), encoding="utf-8")
    (art_root / "acquisition.json").write_text(json.dumps(payload["acquisition"]), encoding="utf-8")
    (art_root / "conditions.json").write_text(json.dumps(payload["conditions"]), encoding="utf-8")
    (art_root / "comparisons.json").write_text(json.dumps(payload["comparisons"]), encoding="utf-8")
    (pay_root / "budget_curve.json").write_text(json.dumps(payload["payloads"]["budget_curve"]), encoding="utf-8")
    (pay_root / "pattern_vs_rate.json").write_text(json.dumps(payload["payloads"]["pattern_vs_rate"]), encoding="utf-8")
    (pay_root / "reliability.json").write_text(json.dumps(payload["payloads"]["reliability"]), encoding="utf-8")
    (pay_root / "decision_loss.json").write_text(json.dumps(payload["payloads"]["decision_loss"]), encoding="utf-8")

    # Valid check passes
    vg3.validate_database_projections(payload, art_root, pay_root)

    # Disagreeing disk file rejected
    (pay_root / "decision_loss.json").write_text(json.dumps({"loss": 999.0}), encoding="utf-8")
    with pytest.raises(AssertionError, match="Database projection decision_loss does not match saved artifact"):
        vg3.validate_database_projections(payload, art_root, pay_root)


def test_validate_logical_content_and_experiment_id():
    from shiftguard.experiments.ids import stable_hash

    payload = {"foo": "bar", "data": [1, 2, 3]}
    expected_logical = stable_hash(payload)
    expected_exp_id = expected_logical[:24]

    # Valid check passes
    vg3.validate_logical_content_and_experiment_id(
        payload,
        {"logical_content": expected_logical},
        expected_exp_id,
    )

    # Tampered logical content digest rejected
    with pytest.raises(AssertionError, match="Logical content digest mismatch"):
        vg3.validate_logical_content_and_experiment_id(
            payload,
            {"logical_content": "tampered_digest"},
            expected_exp_id,
        )

    # Tampered experiment id rejected
    with pytest.raises(AssertionError, match="Experiment ID mismatch"):
        vg3.validate_logical_content_and_experiment_id(
            payload,
            {"logical_content": expected_logical},
            "tampered_exp_id",
        )

