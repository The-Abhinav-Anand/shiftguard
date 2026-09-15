from __future__ import annotations

import numpy as np
import hashlib
import json
from dataclasses import replace
import pytest

from shiftguard.calibration.base import CalibrationRecord
from shiftguard.calibration.sklearn_maps import CalibrationFit, fit_temperature, frozen_pipeline, predict_with_fallback
from shiftguard.datasets.bank import BankDataset
from shiftguard.experiments.config import OutageConfig
from shiftguard.experiments.outage_runner import _condition, _comparison, _fitted_state, prepare_outage_handoff, run_outage_recovery
from shiftguard.experiments.evaluator import FinalTestEvaluator
from shiftguard.experiments.ids import stable_hash
from shiftguard.storage.repositories import ExperimentRepository
from shiftguard.predictors.logistic import fit_initial_logistic_regression
from shiftguard.preprocessing.tabular import fit_train_preprocessor


def _dataset() -> BankDataset:
    rows = []
    for row_id in range(1, 601):
        rows.append({"row_id": row_id, "age": str(20 + row_id % 50), "job": "admin." if row_id % 2 else "technician", "marital": "single" if row_id % 3 else "married", "education": "secondary", "default": "no", "housing": "yes", "loan": "no", "pdays": "999" if row_id % 4 else "5", "previous": str(row_id % 3), "poutcome": "nonexistent" if row_id % 4 else "success", "y": row_id % 2})
    return BankDataset(rows, "raw-fixture", "clean-fixture")


def test_outage_recovery_pairs_masks_and_persists_fallback_ready_conditions(tmp_path) -> None:
    config = OutageConfig(master_seed=31001, artifact_root=tmp_path / "artifacts")
    result = run_outage_recovery(prepare_outage_handoff(_dataset(), config), config, f"sqlite:///{tmp_path / 'outage.db'}")

    assert set(result.conditions) == {"no_outage_raw", "no_outage_source_temperature", "outage_raw", "outage_source_temperature", "outage_target_temperature"}
    assert result.conditions["outage_raw"]["mask_id"] == result.conditions["outage_source_temperature"]["mask_id"] == result.conditions["outage_target_temperature"]["mask_id"]
    assert result.conditions["outage_target_temperature"]["calibration"]["labels_consumed"] == 50
    assert result.conditions["no_outage_source_temperature"]["calibration"]["fit_status"] == "fitted"
    assert result.conditions["outage_target_temperature"]["calibration"]["fit_status"] == "fitted"
    assert set(result.comparisons) == {"outage_damage_raw", "outage_damage_source", "source_calibration_under_outage", "target_adaptation_vs_source", "target_adaptation_vs_raw", "restoration_vs_no_outage_source"}
    assert "logical_content" in result.content_hashes
    for name in ("config", "seeds", "masks", "acquisition", "metadata", "conditions", "comparisons"):
        assert result.content_hashes[name] == hashlib.sha256((tmp_path / "artifacts" / result.experiment_id / f"{name}.json").read_bytes()).hexdigest()


def test_temperature_one_class_falls_back_without_refitting_predictor() -> None:
    dataset = _dataset()
    train = [{key: value for key, value in row.items() if key != "y"} for row in dataset.rows[:100]]
    labels = [int(row["y"]) for row in dataset.rows[:100]]
    preprocessor = fit_train_preprocessor(train)
    predictor = fit_initial_logistic_regression(preprocessor.transform(train), labels, seed=7)
    coefficients = predictor.coef_.copy()
    fitted = fit_temperature(frozen_pipeline(preprocessor, predictor), tuple(train[:10]), tuple([1] * 10), "target_temperature")

    assert fitted.record.fit_status == "not_fitted"
    assert fitted.record.resolved_method == "raw"
    assert np.array_equal(predictor.coef_, coefficients)


def test_target_one_class_uses_fitted_source_without_redraw() -> None:
    dataset = _dataset()
    train = [{key: value for key, value in row.items() if key != "y"} for row in dataset.rows[:100]]
    labels = [int(row["y"]) for row in dataset.rows[:100]]
    preprocessor = fit_train_preprocessor(train)
    predictor = fit_initial_logistic_regression(preprocessor.transform(train), labels, seed=7)
    pipeline = frozen_pipeline(preprocessor, predictor)
    source = fit_temperature(pipeline, tuple(train[:50]), tuple(labels[:50]), "source_temperature")
    target = fit_temperature(pipeline, tuple(train[50:60]), tuple([1] * 10), "target_temperature")
    resolved, _ = predict_with_fallback(pipeline, source, target, tuple(train[:10]))

    assert source.record.fit_status == "fitted"
    assert target.record.fit_status == "not_fitted"
    assert resolved["target_temperature"].resolved_method == "source_temperature"
    assert target.record.labels_consumed == 10


def test_successful_source_and_target_fit_freeze_original_pipeline_state() -> None:
    handoff = prepare_outage_handoff(_dataset(), OutageConfig(master_seed=31001))
    preprocessor = fit_train_preprocessor(list(handoff.train_features))
    predictor = fit_initial_logistic_regression(preprocessor.transform(list(handoff.train_features)), list(handoff.train_labels), 7)
    pipeline = frozen_pipeline(preprocessor, predictor)
    before = stable_hash(_fitted_state(preprocessor, predictor))
    source = fit_temperature(pipeline, handoff.source_features, handoff.source_labels, "source_temperature")
    acquired = handoff.target_provider.reveal_prefix(50)
    from shiftguard.missingness.block import history_block_mask
    masked = history_block_mask(acquired.record_ids, 7, 0.5).apply(acquired.features)
    target = fit_temperature(pipeline, masked, acquired.labels, "target_temperature")
    assert source.record.fit_status == target.record.fit_status == "fitted"
    assert source.probability_map.estimator.estimator is pipeline
    assert target.probability_map.estimator.estimator is pipeline
    assert target.probability_map is not source.probability_map
    predict_with_fallback(pipeline, source, target, masked)
    assert stable_hash(_fitted_state(preprocessor, predictor)) == before


class _Map:
    def __init__(self, failure=None):
        self.failure = failure
        self.calls = 0

    def predict_proba(self, features):
        self.calls += 1
        if self.failure == "exception":
            raise RuntimeError("fixture_prediction_failure")
        if self.failure == "nonfinite":
            return np.full((len(features), 2), np.nan)
        return np.tile([0.7, 0.3], (len(features), 1))


@pytest.mark.parametrize("source_failure,target_failure,source_fitted,target_fitted,raw_failure,resolved", [
    (None, "exception", True, True, None, "source_temperature"),
    ("nonfinite", "exception", True, True, None, "raw"),
    (None, None, False, False, None, "raw"),
    ("exception", None, True, False, None, "raw"),
    ("exception", "exception", True, True, "exception", None),
])
def test_prediction_cascade_is_label_free_and_source_reuse_is_not_retried(
    source_failure, target_failure, source_fitted, target_fitted, raw_failure, resolved,
) -> None:
    rows = prepare_outage_handoff(_dataset(), OutageConfig(master_seed=31001)).final_features[:4]
    raw, source_map, target_map = _Map(raw_failure), _Map(source_failure), _Map(target_failure)
    source = CalibrationFit(source_map, CalibrationRecord("source_temperature", "source_temperature", "fitted" if source_fitted else "not_fitted", "one_class" if not source_fitted else None, 90, 1.0))
    target = CalibrationFit(target_map, CalibrationRecord("target_temperature", "target_temperature", "fitted" if target_fitted else "not_fitted", "one_class" if not target_fitted else None, 50, 1.0))
    predictions, attempts = predict_with_fallback(raw, source, target, rows)
    assert predictions["target_temperature"].resolved_method == resolved
    assert source_map.calls == int(source_fitted)
    assert target_map.calls == int(target_fitted)
    assert raw.calls == 1
    assert len(attempts) == 1 + int(source_fitted) + int(target_fitted)
    if resolved is None:
        class NeverEvaluator:
            def score(self, probabilities):
                pytest.fail("failed raw predictions must never reach final labels")
        condition = _condition("failed", predictions["target_temperature"], NeverEvaluator(), target.record, "mask", {"dataset": "a"}, "map")
        assert condition["metrics"] is None and condition["status"] == "failed"
        comparison = _comparison("unavailable", condition, condition)
        assert comparison["deltas"] is None and comparison["available"] is False


def test_evaluator_exception_is_never_a_fallback_signal() -> None:
    class RejectEvaluator:
        def score(self, probabilities):
            raise RuntimeError("evaluator_error")
    from shiftguard.calibration.sklearn_maps import PredictionResolution
    with pytest.raises(RuntimeError, match="evaluator_error"):
        _condition("raw", PredictionResolution([0.3], "raw", ()), RejectEvaluator(),
                   CalibrationRecord("raw", "raw", "not_applicable", None, 0, None), None, {}, "id")


def test_full_pool_mask_before_single_reveal_and_repeatable_persistence(tmp_path, monkeypatch) -> None:
    import shiftguard.experiments.outage_runner as runner
    config = OutageConfig(master_seed=31001, artifact_root=tmp_path / "artifacts")
    dataset = _dataset()
    handoff = prepare_outage_handoff(dataset, config)
    assert all("y" not in row for row in handoff.final_features)
    assert all("y" not in row for row in handoff.target_provider.pool_features)
    assert not hasattr(handoff, "rows")
    mask_events = []
    original_mask = runner.history_block_mask
    original_reveal = handoff.target_provider.reveal_prefix
    def mask(ids, seed, probability):
        mask_events.append(ids)
        return original_mask(ids, seed, probability)
    def reveal(count):
        assert mask_events == [handoff.target_provider.pool_record_ids]
        assert count == 50
        return original_reveal(count)
    monkeypatch.setattr(runner, "history_block_mask", mask)
    monkeypatch.setattr(handoff.target_provider, "reveal_prefix", reveal)
    database = f"sqlite:///{tmp_path / 'repeat.db'}"
    monkeypatch.setattr(runner, "audit_provenance", lambda: {"execution": "first"})
    first = run_outage_recovery(handoff, config, database)
    root = config.artifact_root / first.experiment_id
    saved = {name: (root / f"{name}.json").read_bytes() for name in first.content_hashes if name != "logical_content"}
    monkeypatch.setattr(runner, "audit_provenance", lambda: {"execution": "second"})
    second = run_outage_recovery(prepare_outage_handoff(dataset, config), config, database)
    assert first.experiment_id == second.experiment_id
    assert first.content_hashes == second.content_hashes
    assert first.execution_id != second.execution_id
    assert all((root / f"{name}.json").read_bytes() == value for name, value in saved.items())
    masks = json.loads(saved["masks"])
    pool = masks["full_pool"]
    assert len(pool["record_ids"]) == len(handoff.roles["target_pool"]) > 50
    selected = dict(zip(pool["record_ids"], pool["selected"]))
    subset = masks["acquired_subset"]
    assert subset["rates"]["selected_rows"] == sum(selected[row_id] for row_id in subset["record_ids"])
    assert subset["parent_mask_id"] == pool["mask_id"]
    assert set(pool["record_ids"]).isdisjoint(masks["test"]["record_ids"])
    repository = ExperimentRepository.from_url(database)
    try:
        stored = repository.get(first.experiment_id)
        assert stored.content_hashes == first.content_hashes
        assert len(repository.execution_ids(first.experiment_id)) == 2
        from sqlalchemy import text
        with repository.engine.connect() as connection:
            audits = [json.loads(row[0])["provenance"]["execution"] for row in connection.execute(text("SELECT audit_json FROM experiment_executions"))]
        assert set(audits) == {"first", "second"}
    finally:
        repository.dispose()


@pytest.mark.parametrize("fit_failed", [True, False])
def test_runner_failure_counts_no_redraw_and_final_label_isolation(tmp_path, monkeypatch, fit_failed) -> None:
    import shiftguard.experiments.outage_runner as runner
    config = OutageConfig(master_seed=31001, artifact_root=tmp_path / "artifacts")
    handoff = prepare_outage_handoff(_dataset(), config)
    reveals = []
    original_reveal = handoff.target_provider.reveal_prefix
    def reveal(count):
        reveals.append(count)
        return original_reveal(count)
    monkeypatch.setattr(handoff.target_provider, "reveal_prefix", reveal)
    maps = []
    def fit(pipeline, rows, labels, method):
        assert all("y" not in row for row in rows)
        assert not set(int(row.get("row_id", -1)) for row in rows).intersection(handoff.roles["final_test"])
        probability_map = _Map("exception")
        maps.append(probability_map)
        return CalibrationFit(probability_map, CalibrationRecord(method, method, "not_fitted" if fit_failed else "fitted", "fixture_fit_failure" if fit_failed else None, len(labels), None if fit_failed else 1.0))
    monkeypatch.setattr(runner, "fit_temperature", fit)
    first = run_outage_recovery(handoff, config, f"sqlite:///{tmp_path / 'failure.db'}")
    assert reveals == [50]
    assert [item.calls for item in maps] == ([0, 0] if fit_failed else [2, 1])
    metadata = json.loads((config.artifact_root / first.experiment_id / "metadata.json").read_bytes())
    counts = metadata["fallback_counts"]
    assert counts["source_temperature"]["fit_failure_count"] == int(fit_failed)
    assert counts["target_temperature"]["fit_failure_count"] == int(fit_failed)
    assert counts["source_temperature"]["prediction_failure_count"] == (0 if fit_failed else 2)
    assert counts["target_temperature"]["prediction_failure_count"] == (0 if fit_failed else 1)
    condition = first.conditions["outage_target_temperature"]
    assert condition["calibration"]["labels_consumed"] == 50
    assert condition["calibration"]["resolved_method"] == "raw"
    assert [failure["method"] for failure in condition["calibration"]["fallback_reason"]] == ["target_temperature", "source_temperature"]
    # Swapping only evaluator outcomes cannot change masks, fit records, or resolution.
    changed = replace(prepare_outage_handoff(_dataset(), config), evaluator=FinalTestEvaluator(tuple([0] * len(handoff.final_features))))
    second = run_outage_recovery(changed, config, f"sqlite:///{tmp_path / 'failure.db'}")
    for artifact in ("metadata", "masks", "acquisition"):
        assert first.content_hashes[artifact] == second.content_hashes[artifact]
    assert first.conditions["outage_raw"]["metrics"] != second.conditions["outage_raw"]["metrics"]


def test_condition_identity_binds_dataset_evaluation_rows_and_predictor() -> None:
    from shiftguard.calibration.sklearn_maps import PredictionResolution
    prediction = PredictionResolution([0.3], "raw", ())
    record = CalibrationRecord("raw", "raw", "not_applicable", None, 0, None)
    context = {"dataset_id": "data", "evaluation_rows_id": "rows", "predictor_id": "model"}
    def identity(value):
        return _condition("raw", prediction, FinalTestEvaluator((0,)), record, None, value, "map")["condition_id"]
    assert all(identity({**context, field: "changed"}) != identity(context) for field in context)


def test_optimizer_failure_records_not_fitted_without_retry(monkeypatch) -> None:
    from sklearn.calibration import CalibratedClassifierCV
    handoff = prepare_outage_handoff(_dataset(), OutageConfig(master_seed=31001))
    preprocessor = fit_train_preprocessor(list(handoff.train_features))
    predictor = fit_initial_logistic_regression(preprocessor.transform(list(handoff.train_features)), list(handoff.train_labels), 7)
    pipeline = frozen_pipeline(preprocessor, predictor)
    calls = []
    def fail(self, features, labels):
        calls.append(len(labels))
        raise RuntimeError("optimizer_fixture_failure")
    monkeypatch.setattr(CalibratedClassifierCV, "fit", fail)
    fitted = fit_temperature(pipeline, handoff.source_features, handoff.source_labels, "source_temperature")
    assert calls == [len(handoff.source_labels)]
    assert fitted.record.fit_status == "not_fitted"
    assert fitted.record.labels_consumed == len(handoff.source_labels)
    assert "optimizer_fixture_failure" in fitted.record.fallback_reason


def test_runner_persists_complete_raw_failure_as_null_without_evaluation(tmp_path, monkeypatch) -> None:
    import shiftguard.experiments.outage_runner as runner
    config = OutageConfig(master_seed=31001, artifact_root=tmp_path / "artifacts")
    class NeverEvaluator:
        def score(self, probabilities):
            pytest.fail("failed prediction must not be evaluated")
    handoff = replace(prepare_outage_handoff(_dataset(), config), evaluator=NeverEvaluator())
    monkeypatch.setattr(runner, "frozen_pipeline", lambda *args: _Map("exception"))
    def no_fit(pipeline, rows, labels, method):
        return CalibrationFit(pipeline, CalibrationRecord(method, "raw", "not_fitted", "fixture_fit_failure", len(labels), None))
    monkeypatch.setattr(runner, "fit_temperature", no_fit)
    database = f"sqlite:///{tmp_path / 'all-failed.db'}"
    result = run_outage_recovery(handoff, config, database)
    assert all(c["status"] == "failed" and c["metrics"] is None for c in result.conditions.values())
    assert all(c["deltas"] is None and not c["available"] for c in result.comparisons.values())
    repository = ExperimentRepository.from_url(database)
    try:
        persisted = repository.get(result.experiment_id).deterministic_payload
        assert all(c["metrics"] is None for c in persisted["conditions"].values())
    finally:
        repository.dispose()
