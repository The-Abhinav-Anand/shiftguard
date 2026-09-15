from __future__ import annotations

from shiftguard.missingness.block import HISTORY_FEATURES, history_block_mask
from shiftguard.preprocessing.tabular import fit_train_preprocessor


def test_history_block_masks_raw_features_and_preserves_unrelated_values() -> None:
    rows = (
        {"row_id": 1, "age": "30", "job": "admin.", "marital": "single", "education": "secondary", "default": "no", "housing": "yes", "loan": "no", "pdays": "999", "previous": "0", "poutcome": "nonexistent"},
        {"row_id": 2, "age": "40", "job": "technician", "marital": "married", "education": "tertiary", "default": "no", "housing": "no", "loan": "no", "pdays": "5", "previous": "2", "poutcome": "success"},
    )
    mask = history_block_mask((1, 2), seed=7, row_probability=1.0)
    transformed = mask.apply(rows)

    assert mask.features == HISTORY_FEATURES
    assert all(row[feature] is None for row in transformed for feature in HISTORY_FEATURES)
    assert [row["age"] for row in transformed] == ["30", "40"]
    assert mask.rates(rows)["observed_history_group_new_missing_rate"] == 1.0
    assert mask.rates(rows)["observed_all_feature_cells_new_missing_rate"] == 0.3
    preprocessor = fit_train_preprocessor([dict(rows[0]), dict(rows[1])])
    assert preprocessor.transform(list(transformed)).shape[0] == 2


def test_history_mask_is_deterministic_and_rate_bounded() -> None:
    first = history_block_mask((1, 2, 3, 4), seed=11, row_probability=0.5)
    second = history_block_mask((1, 2, 3, 4), seed=11, row_probability=0.5)

    assert first == second
    assert first.mask_id == second.mask_id


def test_rates_count_natural_missingness_inside_and_outside_history() -> None:
    from shiftguard.datasets.bank import BANK_FEATURES
    from shiftguard.missingness.base import RawFeatureMask

    rows = tuple({"row_id": index, **dict.fromkeys(BANK_FEATURES, "observed")} for index in (1, 2, 3))
    rows[0].update(pdays=None, age="")
    rows[1].update(poutcome="", job=None)
    mask = RawFeatureMask((1, 2, 3), HISTORY_FEATURES, (True, False, True), 0.5)
    rates = mask.rates(rows)
    assert rates["row_count"] == 3
    assert rates["selected_rows"] == 2
    assert rates["all_feature_cells"] == 30
    assert rates["observed_all_feature_cells"] == 26
    assert rates["observed_history_eligible_cells"] == 7
    assert rates["natural_missing_inside_history_cells"] == 2
    assert rates["natural_missing_outside_history_cells"] == 2
    assert rates["newly_missing_cells"] == 5
    assert rates["observed_all_feature_cells_new_missing_rate"] == 5 / 26
    assert rates["observed_history_group_new_missing_rate"] == 5 / 7
    assert rates["total_missing_cells"] == 9
    assert rates["total_missing_rate_over_all_feature_cells"] == 9 / 30
    subset = mask.rates(rows[1:2])
    assert subset["selected_rows"] == 0
    assert subset["realized_selected_row_fraction"] == 0
    assert subset["newly_missing_cells"] == 0
