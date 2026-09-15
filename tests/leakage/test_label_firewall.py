from __future__ import annotations

import numpy as np
import pytest

from shiftguard.datasets.bank import BANK_FEATURES
from shiftguard.datasets.registry import select_nested_prefix
from shiftguard.experiments.config import DEVELOPMENT_SEEDS, CONFIRMATORY_SEEDS
from shiftguard.preprocessing.tabular import fit_train_preprocessor
from shiftguard.preprocessing.tabular import feature_rows
from shiftguard.datasets.bank import BankDataset
from shiftguard.experiments.config import BaselineConfig
from shiftguard.experiments.runner import prepare_baseline_handoff


def test_acquisition_is_label_blind_and_nested() -> None:
    row_ids = tuple(range(1, 21))
    prefix_5 = select_nested_prefix(row_ids, seed=22, count=5)
    prefix_10 = select_nested_prefix(row_ids, seed=22, count=10)

    assert prefix_5 == prefix_10[:5]


def test_development_and_confirmatory_seed_sets_are_disjoint() -> None:
    assert set(DEVELOPMENT_SEEDS).isdisjoint(CONFIRMATORY_SEEDS)


def test_preprocessor_handles_heldout_categories_without_mutating_train_statistics() -> None:
    train_rows = [
        {feature: "known" for feature in BANK_FEATURES} | {"age": "20", "pdays": "999", "previous": "0"},
        {feature: "known" for feature in BANK_FEATURES} | {"age": "40", "pdays": "10", "previous": "2"},
    ]
    preprocessor = fit_train_preprocessor(train_rows)
    numeric = preprocessor.transformer.named_transformers_["numeric"]
    categories = tuple(tuple(values) for values in preprocessor.transformer.named_transformers_["categorical"].categories_)
    medians = tuple(numeric.named_steps["imputer"].statistics_)

    transformed = preprocessor.transform([
        {feature: "heldout" for feature in BANK_FEATURES} | {"age": "", "pdays": "999", "previous": ""},
        {feature: None for feature in BANK_FEATURES} | {"age": "30", "pdays": "999", "previous": "0"},
    ])

    assert np.isfinite(transformed).all()
    assert tuple(numeric.named_steps["imputer"].statistics_) == medians
    assert tuple(tuple(values) for values in preprocessor.transformer.named_transformers_["categorical"].categories_) == categories


def test_feature_projection_removes_final_labels_before_model_boundaries() -> None:
    rows = [{feature: "value" for feature in BANK_FEATURES} | {"age": "30", "pdays": "999", "previous": "0", "y": 1}]

    projected = feature_rows(rows)

    assert "y" not in projected[0]
    assert set(projected[0]) == set(BANK_FEATURES)


def test_prepared_handoff_exposes_only_train_labels_and_heldout_features() -> None:
    rows = []
    for row_id in range(1, 101):
        rows.append({feature: "value" for feature in BANK_FEATURES} | {"row_id": row_id, "age": str(20 + row_id % 40), "pdays": "999", "previous": "0", "y": row_id % 2})
    handoff = prepare_baseline_handoff(BankDataset(rows=rows, raw_hash="raw", clean_hash="clean"), BaselineConfig(master_seed=31001))

    assert not hasattr(handoff, "final_rows")
    assert all("y" not in row for row in handoff.train_features)
    assert all("y" not in row for row in handoff.final_features)
    assert len(handoff.train_labels) == len(handoff.train_features)
