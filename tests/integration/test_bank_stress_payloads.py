from __future__ import annotations

import hashlib
import json
from pathlib import Path
import pytest

from shiftguard.datasets.bank import BankDataset
from shiftguard.experiments.config import StressConfig
from shiftguard.experiments.stress_runner import run_stress_engine
from shiftguard.storage.repositories import ExperimentRepository


def _synthetic_bank_dataset(n: int = 600) -> BankDataset:
    rows = []
    for row_id in range(1, n + 1):
        rows.append({
            "row_id": row_id,
            "age": str(20 + row_id % 50),
            "job": "admin." if row_id % 2 else "technician",
            "marital": "single" if row_id % 3 else "married",
            "education": "secondary",
            "default": "no",
            "housing": "yes",
            "loan": "no",
            "pdays": "999" if row_id % 4 else "5",
            "previous": str(row_id % 3),
            "poutcome": "nonexistent" if row_id % 4 else "success",
            "y": row_id % 2,
        })
    return BankDataset(rows, "raw-hash-fixture", "clean-hash-fixture")


def test_stress_engine_produces_all_conditions_and_four_payloads(tmp_path: Path) -> None:
    dataset = _synthetic_bank_dataset(600)
    config = StressConfig(
        master_seed=31001,
        artifact_root=tmp_path / "artifacts",
        predictors=("logistic_regression", "random_forest"),
        budgets=(0, 25, 50),
        mcar_rates=(0.0, 0.1),
    )
    db_url = f"sqlite:///{tmp_path / 'stress.db'}"

    result = run_stress_engine(dataset, config, db_url)

    # 1. Condition verification
    assert len(result.conditions) > 0

    # Verify all 8 methods are represented
    for method in config.calibration_methods:
        matching = [k for k in result.conditions if k.endswith(f"__{method}")]
        assert len(matching) > 0, f"Method {method} missing from conditions"

    # Verify budget 0 behavior: consumes 0 target labels
    for k, cond in result.conditions.items():
        if "__b0__" in k:
            assert cond["labels_consumed"] == 0
            if cond["requested_method"].startswith("target_"):
                # Target methods at budget 0 must have resolved to fallback
                assert cond["resolved_method"] != cond["requested_method"]

    # 2. Four analytical payloads verification
    assert "budget_curve" in result.payloads
    assert "pattern_vs_rate" in result.payloads
    assert "reliability" in result.payloads
    assert "decision_loss" in result.payloads

    # Verify budget curve contains entries for all budgets
    bc = result.payloads["budget_curve"]
    assert "scenarios" in bc
    first_scen = next(iter(bc["scenarios"].values()))
    for method in config.calibration_methods:
        assert method in first_scen
        assert len(first_scen[method]) == len(config.budgets)

    # Verify pattern_vs_rate matching report
    pvr = result.payloads["pattern_vs_rate"]
    assert "matching_report" in pvr
    report = pvr["matching_report"]
    assert report["matching_strategy"] == "bernoulli_matched_rate"
    assert report["matching_status"] in ("within_tolerance", "exact_match")
    assert report["comparison_qualified"] is True
    assert "residual_mismatch" in report
    assert report["residual_mismatch"] >= 0.0

    # Verify reliability payload
    rel = result.payloads["reliability"]
    assert "scenarios" in rel

    # Verify decision loss payload
    dl = result.payloads["decision_loss"]
    assert "scenarios" in dl

    # 3. Artifact byte hashes verification
    exp_dir = tmp_path / "artifacts" / result.experiment_id
    payload_dir = exp_dir / "payloads"

    assert "logical_content" in result.content_hashes
    for name in ("config", "seeds", "masks", "acquisition", "conditions", "comparisons"):
        raw_bytes = (exp_dir / f"{name}.json").read_bytes()
        assert result.content_hashes[name] == hashlib.sha256(raw_bytes).hexdigest()

    for p_name in ("budget_curve", "pattern_vs_rate", "reliability", "decision_loss"):
        raw_bytes = (payload_dir / f"{p_name}.json").read_bytes()
        assert result.content_hashes[p_name] == hashlib.sha256(raw_bytes).hexdigest()

    # 4. Database persistence and reopen
    repo = ExperimentRepository.from_url(db_url)
    try:
        stored = repo.get(result.experiment_id)
        assert stored is not None
        assert stored.content_hashes == result.content_hashes

        # Verify context-bound identities, failure counts, and prefixes after reopen (FIX06)
        d_reopen = stored.deterministic_payload
        assert "revealed_prefixes" in d_reopen["acquisition"]
        assert "0" in d_reopen["acquisition"]["revealed_prefixes"]
        assert len(d_reopen["acquisition"]["revealed_prefixes"]["0"]) == 0
        assert len(d_reopen["acquisition"]["revealed_prefixes"]["25"]) == 25

        # Check conditions in reopened state
        reopen_conds = d_reopen["conditions"]
        for c_key, c_val in reopen_conds.items():
            assert "condition_id" in c_val
            assert "dataset_id" in c_val
            assert "evaluation_rows_id" in c_val
            assert "predictor_id" in c_val
            assert "source_map_id" in c_val
            assert "pool_mask_id" in c_val
            assert "test_mask_id" in c_val
            assert "acquired_record_ids" in c_val
            assert "fitted_parameters" in c_val
            assert "unique_fit_failures" in c_val
            assert "unique_prediction_failures" in c_val

            # At budget 0, unattempted fits must NOT count toward unique_fit_failures
            if c_val["budget"] == 0 and c_val["requested_method"].startswith("target_"):
                assert c_val["fallback_reason"] == "budget_zero_unattempted"
                assert c_val["unique_fit_failures"] == 0

        # Check comparisons qualification after reopen (FIX09)
        pattern_comps = d_reopen["comparisons"]["pattern_comparison"]
        for pred_name, p_data in pattern_comps.items():
            for m_name, m_comp in p_data["methods"].items():
                assert "comparison_qualified" in m_comp
                assert "matching_status" in m_comp
                assert "tolerance" in m_comp
                assert "residual_mismatch" in m_comp
    finally:
        repo.dispose()
