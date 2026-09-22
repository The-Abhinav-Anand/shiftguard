from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

import numpy as np

from shiftguard.calibration.base import CalibrationRecord
from shiftguard.calibration.sklearn_maps import PredictionResolution, fit_temperature, frozen_pipeline, predict_with_fallback
from shiftguard.datasets.bank import BankDataset
from shiftguard.experiments.config import OutageConfig
from shiftguard.experiments.ids import stable_hash
from shiftguard.experiments.runner import _seed_bundle, audit_provenance
from shiftguard.experiments.evaluator import FinalTestEvaluator
from shiftguard.missingness.block import HISTORY_FEATURES, history_block_mask
from shiftguard.predictors.logistic import fit_initial_logistic_regression, predictor_identity
from shiftguard.preprocessing.tabular import feature_rows, fit_train_preprocessor, preprocessing_config
from shiftguard.protocol.acquisition import LabelBlindTargetProvider
from shiftguard.protocol.splits import make_role_splits
from shiftguard.experiments.publication import PublicationService


@dataclass(frozen=True)
class OutageHandoff:
    train_features: tuple[dict[str, str | int], ...]
    train_labels: tuple[int, ...]
    source_features: tuple[dict[str, str | int], ...]
    source_labels: tuple[int, ...]
    final_features: tuple[dict[str, str | int], ...]
    evaluator: FinalTestEvaluator
    target_provider: LabelBlindTargetProvider
    roles: dict[str, tuple[int, ...]]
    raw_hash: str
    clean_hash: str


@dataclass(frozen=True)
class OutageResult:
    experiment_id: str
    execution_id: str
    conditions: dict[str, dict[str, object]]
    comparisons: dict[str, dict[str, object]]
    content_hashes: dict[str, str]


def prepare_outage_handoff(dataset: BankDataset, config: OutageConfig) -> OutageHandoff:
    seeds = _seed_bundle(config.master_seed)
    roles = make_role_splits(dataset.rows, seeds["split"])
    rows_by_id = {int(row["row_id"]): row for row in dataset.rows}
    def rows(role: str) -> tuple[dict[str, str | int], ...]:
        return tuple(rows_by_id[row_id] for row_id in roles[role])
    train, source, pool, final = rows("train"), rows("source_cal"), rows("target_pool"), rows("final_test")
    return OutageHandoff(
        train_features=tuple(feature_rows(list(train))), train_labels=tuple(int(row["y"]) for row in train),
        source_features=tuple(feature_rows(list(source))), source_labels=tuple(int(row["y"]) for row in source),
        final_features=tuple({"row_id": int(row["row_id"]), **feature_rows([row])[0]} for row in final),
        evaluator=FinalTestEvaluator(tuple(int(row["y"]) for row in final)),
        target_provider=LabelBlindTargetProvider(pool, seeds["acquisition"]), roles=roles,
        raw_hash=dataset.raw_hash, clean_hash=dataset.clean_hash,
    )


def _condition(name: str, prediction: PredictionResolution, evaluator: FinalTestEvaluator,
               calibration: CalibrationRecord, mask_id: str | None,
               context: dict[str, str], map_id: str) -> dict[str, object]:
    # All prediction/fallback decisions are fixed before final labels are scored.
    metrics = evaluator.score(prediction.probabilities) if prediction.probabilities is not None else None
    payload = {
        "name": name, "mask_id": mask_id, "context": context, "requested_map_id": map_id,
        "resolved_map_id": (None if prediction.resolved_method is None else
                            context["predictor_id"] if prediction.resolved_method == "raw" else
                            context["source_map_id"] if prediction.resolved_method == "source_temperature" else map_id),
        "calibration": {**calibration.__dict__, "resolved_method": prediction.resolved_method,
                        "fallback_reason": list(prediction.failures) or None},
        "status": "scored" if metrics is not None else "failed", "metrics": metrics,
    }
    return {"condition_id": stable_hash(payload)[:24], **payload}


def _comparison(name: str, later: dict[str, object], earlier: dict[str, object]) -> dict[str, object]:
    later_metrics, earlier_metrics = later["metrics"], earlier["metrics"]
    available = later_metrics is not None and earlier_metrics is not None
    deltas = ({metric: float(later_metrics[metric]) - float(earlier_metrics[metric])
               for metric in ("brier_score", "log_loss")} if available else None)
    payload = {"name": name, "later": later["condition_id"], "earlier": earlier["condition_id"],
               "available": available, "reason": None if available else "failed_condition",
               "deltas": deltas, "lower_is_better": True}
    return {"comparison_id": stable_hash(payload)[:24], **payload}


def _fitted_state(preprocessor, predictor) -> dict[str, object]:
    numeric = preprocessor.transformer.named_transformers_["numeric"]
    categorical = preprocessor.transformer.named_transformers_["categorical"]
    return {
        "numeric_medians": numeric.named_steps["imputer"].statistics_.tolist(),
        "numeric_means": numeric.named_steps["scaler"].mean_.tolist(),
        "numeric_scales": numeric.named_steps["scaler"].scale_.tolist(),
        "categories": [values.tolist() for values in categorical.categories_],
        "coefficients": predictor.coef_.tolist(), "intercepts": predictor.intercept_.tolist(),
        "classes": predictor.classes_.tolist(),
    }


def run_outage_recovery(
    handoff: OutageHandoff,
    config: OutageConfig,
    database_url: str,
    **publish_kwargs,
) -> OutageResult:
    is_cancelled = publish_kwargs.get("is_cancelled")
    if callable(is_cancelled) and is_cancelled():
        raise RuntimeError("Operation cancelled before outage preparation")

    seeds = _seed_bundle(config.master_seed)
    stream_children = np.random.SeedSequence(seeds["mask"]).spawn(2)
    mask_seeds = {"pool": int(stream_children[0].generate_state(1)[0]), "test": int(stream_children[1].generate_state(1)[0])}
    preprocessor = fit_train_preprocessor(list(handoff.train_features))
    predictor = fit_initial_logistic_regression(preprocessor.transform(list(handoff.train_features)), list(handoff.train_labels), seeds["model"])

    if callable(is_cancelled) and is_cancelled():
        raise RuntimeError("Operation cancelled after initial model training")

    pipeline = frozen_pipeline(preprocessor, predictor)
    source_fit = fit_temperature(pipeline, handoff.source_features, handoff.source_labels, "source_temperature")
    raw_record = CalibrationRecord("raw", "raw", "not_applicable", None, 0, None)
    # The full, canonical pool mask is fixed before any label acquisition.
    pool_features = handoff.target_provider.pool_features
    pool_mask = history_block_mask(handoff.target_provider.pool_record_ids, mask_seeds["pool"], config.history_row_probability)
    masked_pool = {int(row["row_id"]): row for row in pool_mask.apply(pool_features)}
    acquired = handoff.target_provider.reveal_prefix(config.target_label_budget)
    test_ids = tuple(int(row["row_id"]) for row in handoff.final_features)
    test_mask = history_block_mask(test_ids, mask_seeds["test"], config.history_row_probability)
    acquired_outage = tuple(masked_pool[row_id] for row_id in acquired.record_ids)
    final_outage = test_mask.apply(handoff.final_features)
    target_fit = fit_temperature(pipeline, acquired_outage, acquired.labels, "target_temperature")
    dataset_identity = {"raw_hash": handoff.raw_hash, "clean_hash": handoff.clean_hash}
    predictor_metadata = {**predictor_identity(predictor), "fitted_state": _fitted_state(preprocessor, predictor)}
    predictor_id = stable_hash({"dataset": dataset_identity, "train_ids": handoff.roles["train"],
                                "preprocessing": preprocessing_config(), "predictor": predictor_metadata})
    order_id = stable_hash({"dataset": dataset_identity, "seed": seeds["acquisition"],
                            "order": handoff.target_provider.order})
    source_map_id = stable_hash({"predictor_id": predictor_id, "calibration_ids": handoff.roles["source_cal"],
                                "record": source_fit.record.__dict__})
    target_map_id = stable_hash({"predictor_id": predictor_id, "order_id": order_id,
                                "acquired_ids": acquired.record_ids, "pool_mask_id": pool_mask.mask_id,
                                "record": target_fit.record.__dict__})
    context = {"dataset_id": stable_hash(dataset_identity), "evaluation_rows_id": stable_hash(test_ids),
               "predictor_id": predictor_id, "source_map_id": source_map_id}

    if callable(is_cancelled) and is_cancelled():
        raise RuntimeError("Operation cancelled before predictions")

    # Predict each map once per regime. Reuse the source result within the target cascade.
    clean_predictions, clean_attempts = predict_with_fallback(pipeline, source_fit, None, handoff.final_features)
    outage_predictions, outage_attempts = predict_with_fallback(pipeline, source_fit, target_fit, final_outage)
    conditions = {
        "no_outage_raw": _condition("no_outage_raw", clean_predictions["raw"], handoff.evaluator, raw_record, None, context, predictor_id),
        "no_outage_source_temperature": _condition("no_outage_source_temperature", clean_predictions["source_temperature"], handoff.evaluator, source_fit.record, None, context, source_map_id),
        "outage_raw": _condition("outage_raw", outage_predictions["raw"], handoff.evaluator, raw_record, test_mask.mask_id, context, predictor_id),
        "outage_source_temperature": _condition("outage_source_temperature", outage_predictions["source_temperature"], handoff.evaluator, source_fit.record, test_mask.mask_id, context, source_map_id),
        "outage_target_temperature": _condition("outage_target_temperature", outage_predictions["target_temperature"], handoff.evaluator, target_fit.record, test_mask.mask_id, {**context, "acquisition_order_id": order_id}, target_map_id),
    }
    comparisons = {
        "outage_damage_raw": _comparison("outage_damage_raw", conditions["outage_raw"], conditions["no_outage_raw"]),
        "outage_damage_source": _comparison("outage_damage_source", conditions["outage_source_temperature"], conditions["no_outage_source_temperature"]),
        "source_calibration_under_outage": _comparison("source_calibration_under_outage", conditions["outage_source_temperature"], conditions["outage_raw"]),
        "target_adaptation_vs_source": _comparison("target_adaptation_vs_source", conditions["outage_target_temperature"], conditions["outage_source_temperature"]),
        "target_adaptation_vs_raw": _comparison("target_adaptation_vs_raw", conditions["outage_target_temperature"], conditions["outage_raw"]),
        "restoration_vs_no_outage_source": _comparison("restoration_vs_no_outage_source", conditions["outage_target_temperature"], conditions["no_outage_source_temperature"]),
    }
    masks = {
        "full_pool": {"mask_id": pool_mask.mask_id, "record_ids": pool_mask.record_ids, "features": pool_mask.features, "selected": pool_mask.selected, "rates": pool_mask.rates(pool_features)},
        "acquired_subset": {"parent_mask_id": pool_mask.mask_id, "record_ids": acquired.record_ids, "rates": pool_mask.rates(acquired.features)},
        "test": {"mask_id": test_mask.mask_id, "record_ids": test_mask.record_ids, "features": test_mask.features, "selected": test_mask.selected, "rates": test_mask.rates(handoff.final_features)},
    }
    acquisition = {"provider_seed": handoff.target_provider.seed, "order_id": order_id, "order": handoff.target_provider.order, "requested_labels": config.target_label_budget, "consumed_labels": len(acquired.labels), "distinct_labels": len(acquired.record_ids), "acquired_ids": acquired.record_ids}
    prediction_attempts = {"no_outage": clean_attempts, "outage": outage_attempts}
    # Fit counts are per unique calibrator; prediction counts are per map/regime.
    # Do not sum per-condition failure chains (source reuse would double count).
    fallback_counts = {}
    for method, fitted in (("source_temperature", source_fit), ("target_temperature", target_fit)):
        attempts = [regime[method] for regime in prediction_attempts.values() if method in regime]
        failed = sum(attempt["status"] == "failed" for attempt in attempts)
        fallback_counts[method] = {
            "fit_failure_count": int(fitted.record.fit_status != "fitted"), "fit_count": 1,
            "fit_failure_rate": float(fitted.record.fit_status != "fitted"),
            "prediction_failure_count": failed, "prediction_attempt_count": len(attempts),
            "prediction_failure_rate": failed / len(attempts) if attempts else None,
        }
    metadata = {"preprocessing": preprocessing_config(), "predictor": predictor_metadata, "predictor_id": predictor_id,
                "source_map": {**source_fit.record.__dict__, "map_id": source_map_id},
                "target_map": {**target_fit.record.__dict__, "map_id": target_map_id},
                "prediction_attempts": prediction_attempts, "fallback_counts": fallback_counts}
    deterministic = {"config": config.to_dict(), "seeds": {**seeds, "mask_streams": mask_seeds}, "dataset": {"raw_hash": handoff.raw_hash, "clean_hash": handoff.clean_hash}, "roles": handoff.roles, "history_features": HISTORY_FEATURES, "masks": masks, "acquisition": acquisition, "metadata": metadata, "conditions": conditions, "comparisons": comparisons, "protocol": {"final_labels_scope": "evaluator only", "target_order": "label blind nested prefix", "raw_masking": "before frozen transformation"}}
    artifact_files = {
        "config.json": config.to_dict(),
        "seeds.json": deterministic["seeds"],
        "masks.json": masks,
        "acquisition.json": acquisition,
        "metadata.json": metadata,
        "conditions.json": conditions,
        "comparisons.json": comparisons,
    }
    execution_id = str(uuid4())
    audit_metadata = {"execution_id": execution_id, "provenance": audit_provenance()}
    experiment_id, generation_id, content_hashes, target_dir = PublicationService.publish(
        artifact_root=config.artifact_root,
        deterministic_payload=deterministic,
        artifact_files=artifact_files,
        execution_id=execution_id,
        audit_metadata=audit_metadata,
        database_url=database_url,
        **publish_kwargs,
    )
    return OutageResult(experiment_id, execution_id, conditions, comparisons, content_hashes)
