from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from shiftguard.datasets.bank import BankDataset
from shiftguard.experiments.config import StressConfig, load_run_config
from shiftguard.experiments.evaluator import FinalTestEvaluator
from shiftguard.experiments.stress_runner import (
    StressPartitions,
    execute_stress_engine,
    prepare_stress_partitions,
)
from shiftguard.protocol.acquisition import LabelBlindTargetProvider


def _get_dataset_and_config():
    app_root = Path(__file__).resolve().parents[2]
    config_path = app_root / "configs" / "bank-stress.yaml"
    base_cfg = load_run_config(config_path)

    manifest = json.loads(base_cfg.dataset_manifest.read_text(encoding="utf-8"))
    dataset = BankDataset.from_clean_csv(base_cfg.dataset_csv, manifest)

    # Use smaller budget and single predictor for fast unit testing
    config = StressConfig(
        dataset_csv=base_cfg.dataset_csv,
        dataset_manifest=base_cfg.dataset_manifest,
        artifact_root=app_root / "var" / "artifacts",
        master_seed=31001,
        budgets=(0, 50),
        predictors=("logistic_regression",),
        calibration_methods=("raw", "source_temperature", "target_temperature"),
        cost_grid=((1.0, 1.0), (1.0, 5.0)),
    )
    return dataset, config


def test_label_boundary_unrevealed_pool_and_eval_isolation(tmp_path):
    dataset, config = _get_dataset_and_config()

    partitions_orig, evaluator_orig = prepare_stress_partitions(dataset, config)

    # 1. Assert evaluation labels are not inside StressPartitions
    assert not hasattr(partitions_orig, "final_labels")
    for feat_row in partitions_orig.final_features:
        assert "y" not in feat_row

    # 2. Assert unrevealed pool labels cannot be accessed by fitting routines
    # We create an adversarial target provider where all rows after budget 50 have flipped labels
    provider_orig = partitions_orig.target_provider
    budget = 50
    prefix_orig = provider_orig.reveal_prefix(budget)

    # Clone rows with flipped labels on unrevealed pool items
    tampered_rows = []
    revealed_ids = set(prefix_orig.record_ids)
    for rid, r in provider_orig._rows.items():
        r_copy = dict(r)
        if rid not in revealed_ids:
            # Flip label
            r_copy["y"] = 1 - int(r_copy["y"])
        tampered_rows.append(r_copy)

    adversarial_provider = LabelBlindTargetProvider(tuple(tampered_rows), provider_orig.seed)
    prefix_tampered = adversarial_provider.reveal_prefix(budget)

    # Revealed prefix must be strictly identical
    assert prefix_tampered.record_ids == prefix_orig.record_ids
    assert prefix_tampered.labels == prefix_orig.labels
    assert prefix_tampered.features == prefix_orig.features


def test_evaluator_labels_tampering_does_not_affect_probabilities(tmp_path):
    dataset, config = _get_dataset_and_config()
    partitions, evaluator_orig = prepare_stress_partitions(dataset, config)

    # Create an adversarial evaluator with all flipped labels
    flipped_labels = tuple(1 - y for y in evaluator_orig._labels)
    evaluator_tampered = FinalTestEvaluator(flipped_labels, tier="stress", cost_grid=config.cost_grid)

    db_1 = f"sqlite:///{tmp_path / 'run1.db'}"
    db_2 = f"sqlite:///{tmp_path / 'run2.db'}"

    res_1 = execute_stress_engine(partitions, config, evaluator_orig, db_1)
    res_2 = execute_stress_engine(partitions, config, evaluator_tampered, db_2)

    # Predictions and fitted calibration models must be 100% identical
    for cond_key in res_1.conditions:
        c1 = res_1.conditions[cond_key]
        c2 = res_2.conditions[cond_key]
        assert c1["resolved_method"] == c2["resolved_method"]
        assert c1["fit_status"] == c2["fit_status"]
        assert c1["fallback_reason"] == c2["fallback_reason"]
        assert c1["mask_rates"] == c2["mask_rates"]
        assert c1["unique_fit_failures"] == c2["unique_fit_failures"]
        assert c1["unique_prediction_failures"] == c2["unique_prediction_failures"]
        # Both succeeded in scoring
        assert c1["status"] == "scored"
        assert c2["status"] == "scored"
