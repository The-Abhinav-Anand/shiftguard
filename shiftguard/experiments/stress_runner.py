from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import numpy as np

from shiftguard.calibration.base import CalibrationRecord
from shiftguard.calibration.beta import fit_beta_calibration
from shiftguard.calibration.fraction_binned import fit_source_fraction_binned_temperature
from shiftguard.calibration.platt_logodds import fit_platt_logodds
from shiftguard.calibration.sklearn_maps import (
    CalibrationFit,
    PredictionResolution,
    fit_isotonic_calibration,
    fit_temperature,
    frozen_pipeline,
    predict_conditions_with_fallback,
)
from shiftguard.calibration.source_remask import (
    fit_source_remasked_temperature,
    generate_source_remasked_dataset,
)
from shiftguard.datasets.bank import BANK_FEATURES, BankDataset
from shiftguard.experiments.artifacts import write_json_artifact
from shiftguard.experiments.config import StressConfig
from shiftguard.experiments.evaluator import FinalTestEvaluator
from shiftguard.experiments.ids import stable_hash
from shiftguard.experiments.runner import _seed_bundle, audit_provenance
from shiftguard.missingness.block import HISTORY_FEATURES, history_block_mask
from shiftguard.missingness.mcar import (
    CellwiseFeatureMask,
    compute_matched_mcar,
    generate_mcar_mask,
    generate_shared_uniforms,
)
from shiftguard.predictors.logistic import fit_initial_logistic_regression, predictor_identity
from shiftguard.predictors.random_forest import fit_initial_random_forest, fitted_rf_state, random_forest_identity
from shiftguard.preprocessing.tabular import (
    feature_rows,
    fit_train_preprocessor,
    fit_tree_preprocessor,
    preprocessing_config,
)
from shiftguard.protocol.acquisition import LabelBlindTargetProvider
from shiftguard.protocol.splits import make_role_splits
from shiftguard.storage.repositories import ExperimentRepository

STRESS_FALLBACK_GRAPH = {
    "raw": None,
    "source_temperature": "raw",
    "source_remasked_temperature": "source_temperature",
    "source_fraction_binned_temperature": "source_remasked_temperature",
    "target_temperature": "source_temperature",
    "target_platt_logodds": "target_temperature",
    "target_beta": "target_platt_logodds",
    "target_isotonic": "target_temperature",
}


@dataclass(frozen=True)
class StressPartitions:
    dataset_identity: dict[str, str]
    roles: dict[str, tuple[int, ...]]
    train_features: tuple[dict[str, str | int | None], ...]
    train_labels: tuple[int, ...]
    source_features: tuple[dict[str, str | int | None], ...]
    source_labels: tuple[int, ...]
    final_features: tuple[dict[str, str | int | None], ...]
    target_provider: LabelBlindTargetProvider
    seeds: dict[str, int]
    mask_seeds: dict[str, int]


@dataclass(frozen=True)
class StressResult:
    experiment_id: str
    execution_id: str
    conditions: dict[str, dict[str, object]]
    comparisons: dict[str, dict[str, object]]
    payloads: dict[str, dict[str, object]]
    content_hashes: dict[str, str]


def _fitted_logistic_state(preprocessor, predictor) -> dict[str, object]:
    numeric = preprocessor.transformer.named_transformers_["numeric"]
    categorical = preprocessor.transformer.named_transformers_["categorical"]
    return {
        "numeric_medians": numeric.named_steps["imputer"].statistics_.tolist(),
        "numeric_scales": numeric.named_steps["scaler"].scale_.tolist(),
        "categories": [values.tolist() for values in categorical.categories_],
        "coefficients": predictor.coef_.tolist(),
        "intercepts": predictor.intercept_.tolist(),
        "classes": predictor.classes_.tolist(),
    }


def _stress_seed_bundle(master_seed: int) -> dict[str, int]:
    names = ("split", "model", "mask", "acquisition", "source_remask")
    children = np.random.SeedSequence(master_seed).spawn(5)
    return {name: int(child.generate_state(1)[0]) for name, child in zip(names, children, strict=True)}


def prepare_stress_partitions(dataset: BankDataset, config: StressConfig) -> tuple[StressPartitions, FinalTestEvaluator]:
    """Prepare raw partitions and isolated evaluator under strict label-access boundary.

    The returned StressPartitions contains training features/labels, source calibration features/labels,
    unlabeled final evaluation features, and a LabelBlindTargetProvider that only reveals labels for
    explicitly requested prefixes. Ground truth evaluation labels are passed strictly and exclusively
    to FinalTestEvaluator and are not present anywhere in StressPartitions.
    """
    seeds = _stress_seed_bundle(config.master_seed)
    seq = np.random.SeedSequence(seeds["mask"])
    mask_children = seq.spawn(4)
    mask_seeds = {
        "pool_block": int(mask_children[0].generate_state(1)[0]),
        "test_block": int(mask_children[1].generate_state(1)[0]),
        "pool_mcar": int(mask_children[2].generate_state(1)[0]),
        "test_mcar": int(mask_children[3].generate_state(1)[0]),
    }

    roles = make_role_splits(dataset.rows, seeds["split"])
    rows_by_id = {int(row["row_id"]): row for row in dataset.rows}

    def get_role_rows(role: str) -> tuple[dict[str, str | int], ...]:
        return tuple(rows_by_id[rid] for rid in roles[role])

    train = get_role_rows("train")
    source = get_role_rows("source_cal")
    pool = get_role_rows("target_pool")
    final = get_role_rows("final_test")

    train_features = tuple(feature_rows(list(train)))
    train_labels = tuple(int(row["y"]) for row in train)
    source_features = tuple({"row_id": int(row["row_id"]), **feature_rows([row])[0]} for row in source)
    source_labels = tuple(int(row["y"]) for row in source)
    final_features = tuple({"row_id": int(row["row_id"]), **feature_rows([row])[0]} for row in final)
    final_labels = tuple(int(row["y"]) for row in final)

    evaluator = FinalTestEvaluator(final_labels, tier="stress", cost_grid=config.cost_grid)
    target_provider = LabelBlindTargetProvider(pool, seeds["acquisition"])

    dataset_identity = {"raw_hash": dataset.raw_hash, "clean_hash": dataset.clean_hash}

    partitions = StressPartitions(
        dataset_identity=dataset_identity,
        roles=roles,
        train_features=train_features,
        train_labels=train_labels,
        source_features=source_features,
        source_labels=source_labels,
        final_features=final_features,
        target_provider=target_provider,
        seeds=seeds,
        mask_seeds=mask_seeds,
    )
    return partitions, evaluator


def execute_stress_engine(
    partitions: StressPartitions,
    config: StressConfig,
    evaluator: FinalTestEvaluator,
    database_url: str,
) -> StressResult:
    """Execute the stress engine under strict boundary rules.

    Calibration fitting scope only has access to:
    - training data & labels
    - source calibration data & labels
    - restricted target provider revealing only requested prefixes
    - unlabeled evaluation features
    Final evaluation scoring happens strictly after probability resolution is finalized.
    """
    dataset_identity = partitions.dataset_identity
    seeds = partitions.seeds
    mask_seeds = partitions.mask_seeds
    roles = partitions.roles
    target_provider = partitions.target_provider
    final_features = partitions.final_features

    order_id = stable_hash({"dataset": dataset_identity, "seed": seeds["acquisition"], "order": target_provider.order})

    pool_record_ids = target_provider.pool_record_ids
    test_record_ids = tuple(int(r["row_id"]) for r in final_features)

    pool_uniforms = generate_shared_uniforms(len(pool_record_ids), len(BANK_FEATURES), mask_seeds["pool_mcar"])
    test_uniforms = generate_shared_uniforms(len(test_record_ids), len(BANK_FEATURES), mask_seeds["test_mcar"])

    # Masks for scenarios
    pool_block_mask = history_block_mask(pool_record_ids, mask_seeds["pool_block"], config.history_row_probability)
    test_block_mask = history_block_mask(test_record_ids, mask_seeds["test_block"], config.history_row_probability)
    test_block_rates = test_block_mask.rates(final_features)

    test_matched_mcar_mask, matched_report = compute_matched_mcar(
        record_ids=test_record_ids,
        rows=final_features,
        block_rates=test_block_rates,
        seed=mask_seeds["test_mcar"],
        features=BANK_FEATURES,
        shared_uniforms=test_uniforms,
    )
    pool_matched_mcar_mask = generate_mcar_mask(
        record_ids=pool_record_ids,
        features=BANK_FEATURES,
        rate=float(matched_report["target_rate"]),
        shared_uniforms=pool_uniforms,
    )

    test_mcar_10 = generate_mcar_mask(test_record_ids, BANK_FEATURES, rate=0.10, shared_uniforms=test_uniforms)
    pool_mcar_10 = generate_mcar_mask(pool_record_ids, BANK_FEATURES, rate=0.10, shared_uniforms=pool_uniforms)
    test_mcar_30 = generate_mcar_mask(test_record_ids, BANK_FEATURES, rate=0.30, shared_uniforms=test_uniforms)
    pool_mcar_30 = generate_mcar_mask(pool_record_ids, BANK_FEATURES, rate=0.30, shared_uniforms=pool_uniforms)

    scenarios = {
        "baseline": {"pool_mask": None, "test_mask": None, "test_rows": final_features},
        "history_block_0_50": {"pool_mask": pool_block_mask, "test_mask": test_block_mask, "test_rows": test_block_mask.apply(final_features)},
        "mcar_matched_history": {"pool_mask": pool_matched_mcar_mask, "test_mask": test_matched_mcar_mask, "test_rows": test_matched_mcar_mask.apply(final_features)},
        "mcar_0_10": {"pool_mask": pool_mcar_10, "test_mask": test_mcar_10, "test_rows": test_mcar_10.apply(final_features)},
        "mcar_0_30": {"pool_mask": pool_mcar_30, "test_mask": test_mcar_30, "test_rows": test_mcar_30.apply(final_features)},
    }

    all_conditions: dict[str, dict[str, object]] = {}
    payload_budget_curve: dict[str, object] = {"scenarios": {}}
    payload_pattern_vs_rate: dict[str, object] = {"matching_report": matched_report, "comparisons": {}}
    payload_reliability: dict[str, object] = {"scenarios": {}}
    payload_decision_loss: dict[str, object] = {"scenarios": {}}

    eligible_count = len(BANK_FEATURES)

    def calc_injected_fractions(orig_rows, masked_rows):
        fracs = []
        for orig, masked in zip(orig_rows, masked_rows, strict=True):
            newly_missing = sum(
                orig.get(feat) not in (None, "") and masked.get(feat) in (None, "")
                for feat in BANK_FEATURES
            )
            fracs.append(newly_missing / eligible_count if eligible_count > 0 else 0.0)
        return np.array(fracs, dtype=float)

    for pred_name in config.predictors:
        # Fit predictor & preprocessor on training partition only
        if pred_name == "logistic_regression":
            preprocessor = fit_train_preprocessor(list(partitions.train_features))
            model = fit_initial_logistic_regression(preprocessor.transform(list(partitions.train_features)), list(partitions.train_labels), seeds["model"])
            pred_meta = {**predictor_identity(model), "fitted_state": _fitted_logistic_state(preprocessor, model)}
            prep_cfg = preprocessing_config("linear")
        else:
            preprocessor = fit_tree_preprocessor(list(partitions.train_features))
            model = fit_initial_random_forest(preprocessor.transform(list(partitions.train_features)), list(partitions.train_labels), seeds["model"])
            pred_meta = {**random_forest_identity(model), "fitted_state": fitted_rf_state(preprocessor, model)}
            prep_cfg = preprocessing_config("tree")

        pipeline = frozen_pipeline(preprocessor, model)
        predictor_id = stable_hash({"dataset": dataset_identity, "train_ids": roles["train"], "preprocessing": prep_cfg, "predictor": pred_meta})

        # Fit Source Calibrators (using source calibration rows only, 0 target labels)
        source_temp_fit = fit_temperature(pipeline, partitions.source_features, partitions.source_labels, "source_temperature")
        remasked_rows, remasked_labels, missing_fractions = generate_source_remasked_dataset(
            partitions.source_features, partitions.source_labels, seed=seeds["source_remask"], features=BANK_FEATURES,
        )
        source_remasked_fit = fit_source_remasked_temperature(pipeline, remasked_rows, remasked_labels)
        source_binned_fit = fit_source_fraction_binned_temperature(
            pipeline=pipeline,
            remasked_rows=remasked_rows,
            remasked_labels=remasked_labels,
            missing_fractions=missing_fractions,
            global_fit=source_remasked_fit,
            n_bins=10,
            min_bin_samples=10,
        )

        source_map_id = stable_hash({"predictor_id": predictor_id, "calibration_ids": roles["source_cal"], "record": source_temp_fit.record.__dict__})
        context_base = {
            "dataset_id": stable_hash(dataset_identity),
            "evaluation_rows_id": stable_hash(test_record_ids),
            "predictor_id": predictor_id,
            "predictor_name": pred_name,
            "source_map_id": source_map_id,
        }

        # Evaluate across scenarios
        for scen_name, scen_data in scenarios.items():
            pool_mask = scen_data["pool_mask"]
            test_mask = scen_data["test_mask"]
            test_rows = scen_data["test_rows"]
            mask_id = getattr(test_mask, "mask_id", None)

            # Injected fractions for evaluation rows
            scen_injected_fractions = calc_injected_fractions(final_features, test_rows)
            eval_new_rate = float(
                test_mask.rates(final_features)["observed_all_feature_cells_new_missing_rate"]
                if test_mask is not None else 0.0
            )

            # Mask pool if scenario specifies a mask
            pool_features = target_provider.pool_features
            if pool_mask is not None:
                masked_pool_features = {int(r["row_id"]): r for r in pool_mask.apply(pool_features)}
                pool_new_rate = float(pool_mask.rates(pool_features)["observed_all_feature_cells_new_missing_rate"])
            else:
                masked_pool_features = {int(r["row_id"]): r for r in pool_features}
                pool_new_rate = 0.0

            scen_budget_curve: dict[str, list[dict[str, object]]] = {m: [] for m in config.calibration_methods}
            scen_reliability: dict[str, object] = {}
            scen_decision_loss: dict[str, object] = {}

            for budget in config.budgets:
                acquired = target_provider.reveal_prefix(budget)
                if budget > 0:
                    acquired_outage = tuple(masked_pool_features[rid] for rid in acquired.record_ids)
                    acq_new_rate = float(
                        pool_mask.rates(acquired.features)["observed_all_feature_cells_new_missing_rate"]
                        if pool_mask is not None else 0.0
                    )
                    target_temp_fit = fit_temperature(pipeline, acquired_outage, acquired.labels, "target_temperature")
                    target_platt_fit = fit_platt_logodds(pipeline, acquired_outage, acquired.labels)
                    target_beta_fit = fit_beta_calibration(pipeline, acquired_outage, acquired.labels)
                    target_iso_fit = fit_isotonic_calibration(pipeline, acquired_outage, acquired.labels)
                else:
                    acquired_outage = ()
                    acq_new_rate = 0.0
                    rec_empty = CalibrationRecord("not_fitted", "not_fitted", "not_fitted", "empty_budget", 0, None)
                    target_temp_fit = CalibrationFit(pipeline, rec_empty)
                    target_platt_fit = CalibrationFit(pipeline, rec_empty)
                    target_beta_fit = CalibrationFit(pipeline, rec_empty)
                    target_iso_fit = CalibrationFit(pipeline, rec_empty)

                fits_map = {
                    "raw": pipeline,
                    "source_temperature": source_temp_fit,
                    "source_remasked_temperature": source_remasked_fit,
                    "source_fraction_binned_temperature": source_binned_fit,
                    "target_temperature": target_temp_fit,
                    "target_platt_logodds": target_platt_fit,
                    "target_beta": target_beta_fit,
                    "target_isotonic": target_iso_fit,
                }

                resolutions, attempts = predict_conditions_with_fallback(
                    fits_map,
                    STRESS_FALLBACK_GRAPH,
                    test_rows,
                    injected_fractions=scen_injected_fractions,
                )

                mask_rates = {
                    "pool_new_missing_rate": pool_new_rate,
                    "acquired_new_missing_rate": acq_new_rate,
                    "eval_new_missing_rate": eval_new_rate,
                }

                fit_failures = {
                    f["method"]
                    for res in resolutions.values()
                    for f in res.failures
                    if f.get("phase") == "fit"
                }
                pred_failures = {
                    f["method"]
                    for res in resolutions.values()
                    for f in res.failures
                    if f.get("phase") == "prediction"
                }
                unique_fit_failures = len(fit_failures)
                unique_prediction_failures = len(pred_failures)

                sparse_bin_diag = None
                if hasattr(source_binned_fit.probability_map, "last_diagnostics"):
                    sparse_bin_diag = dict(source_binned_fit.probability_map.last_diagnostics)

                for method in config.calibration_methods:
                    res = resolutions[method]
                    fit_obj = fits_map[method]
                    cal_rec = fit_obj.record if isinstance(fit_obj, CalibrationFit) else CalibrationRecord("raw", "raw", "not_applicable", None, 0, None)
                    labels_consumed = 0 if method in ("raw", "source_temperature", "source_remasked_temperature", "source_fraction_binned_temperature") else len(acquired.labels)

                    metrics = evaluator.score(res.probabilities, include_stress_metrics=True) if res.probabilities is not None else None
                    status = "scored" if metrics is not None else "failed"

                    cond_key = f"{pred_name}__{scen_name}__b{budget}__{method}"
                    cond_payload = {
                        "name": cond_key,
                        "model_family": "linear" if pred_name == "logistic_regression" else "tree",
                        "predictor": pred_name,
                        "scenario": scen_name,
                        "budget": budget,
                        "mask_id": mask_id,
                        "method": method,
                        "requested_method": method,
                        "resolved_method": res.resolved_method,
                        "fit_status": cal_rec.fit_status,
                        "fallback_reason": cal_rec.fallback_reason,
                        "fallback_chain": [f["method"] for f in res.failures],
                        "mask_rates": mask_rates,
                        "unique_fit_failures": unique_fit_failures,
                        "unique_prediction_failures": unique_prediction_failures,
                        "sparse_bin_diagnostics": sparse_bin_diag if method == "source_fraction_binned_temperature" else None,
                        "labels_consumed": labels_consumed,
                        "failures": list(res.failures),
                        "status": status,
                        "metrics": metrics,
                    }
                    cond_id = stable_hash(cond_payload)[:24]
                    all_conditions[cond_key] = {"condition_id": cond_id, **cond_payload}

                    point = {
                        "condition_id": cond_id,
                        "budget": budget,
                        "labels_consumed": labels_consumed,
                        "requested_method": method,
                        "resolved_method": res.resolved_method,
                        "status": status,
                        "available": (status == "scored"),
                        "brier_score": metrics["brier_score"] if metrics else None,
                        "log_loss": metrics["log_loss"] if metrics else None,
                        "ece": metrics["ece"] if metrics else None,
                        "roc_auc": metrics["roc_auc"] if metrics else None,
                        "average_precision": metrics["average_precision"] if metrics else None,
                        "decision_loss_threshold_0_5": (metrics["decision_loss"][0]["loss"] if metrics and metrics.get("decision_loss") else None),
                    }
                    scen_budget_curve[method].append(point)

                    if budget == 50 or (budget == 0 and method.startswith("source_")):
                        if method not in scen_reliability:
                            scen_reliability[method] = {
                                "condition_id": cond_id,
                                "reliability_bins": metrics["reliability"] if metrics else None,
                                "ece": metrics["ece"] if metrics else None,
                            }
                            scen_decision_loss[method] = {
                                "condition_id": cond_id,
                                "cost_grid_losses": metrics["decision_loss"] if metrics else None,
                            }

            payload_budget_curve["scenarios"][f"{pred_name}__{scen_name}"] = scen_budget_curve
            payload_reliability["scenarios"][f"{pred_name}__{scen_name}"] = scen_reliability
            payload_decision_loss["scenarios"][f"{pred_name}__{scen_name}"] = scen_decision_loss

        # Pattern vs Rate comparison (history_block_0_50 vs mcar_matched_history at budget 50)
        p_block = f"{pred_name}__history_block_0_50__b50"
        p_cell = f"{pred_name}__mcar_matched_history__b50"
        payload_pattern_vs_rate["comparisons"][pred_name] = {
            "block_scenario": "history_block_0_50",
            "cellwise_scenario": "mcar_matched_history",
            "budget": 50,
            "methods": {},
        }
        for m in config.calibration_methods:
            block_cond = all_conditions[f"{p_block}__{m}"]
            cell_cond = all_conditions[f"{p_cell}__{m}"]
            block_m = block_cond["metrics"]
            cell_m = cell_cond["metrics"]
            available = (block_m is not None and cell_m is not None)
            method_comp = {
                "available": available,
                "block_condition_id": block_cond["condition_id"],
                "cellwise_condition_id": cell_cond["condition_id"],
                "block_brier": block_m["brier_score"] if block_m else None,
                "cellwise_brier": cell_m["brier_score"] if cell_m else None,
                "delta_brier": (
                    float(block_m["brier_score"]) - float(cell_m["brier_score"])
                    if available else None
                ),
                "block_log_loss": block_m["log_loss"] if block_m else None,
                "cellwise_log_loss": cell_m["log_loss"] if cell_m else None,
            }
            if not available:
                method_comp["unavailability_reason"] = "condition_metrics_unavailable"
            payload_pattern_vs_rate["comparisons"][pred_name]["methods"][m] = method_comp

    comparisons = {
        "pattern_comparison": payload_pattern_vs_rate["comparisons"],
    }

    payloads = {
        "budget_curve": payload_budget_curve,
        "pattern_vs_rate": payload_pattern_vs_rate,
        "reliability": payload_reliability,
        "decision_loss": payload_decision_loss,
    }

    masks_summary = {
        "history_block_test_rates": test_block_rates,
        "mcar_matched_test_rates": test_matched_mcar_mask.rates(final_features),
        "mcar_0_10_test_rates": test_mcar_10.rates(final_features),
        "mcar_0_30_test_rates": test_mcar_30.rates(final_features),
    }

    acquisition_summary = {
        "provider_seed": target_provider.seed,
        "order_id": order_id,
        "order_length": len(target_provider.order),
        "supported_budgets": list(config.budgets),
    }

    deterministic = {
        "config": config.to_dict(),
        "seeds": {**seeds, "mask_streams": mask_seeds},
        "dataset": dataset_identity,
        "roles": roles,
        "history_features": HISTORY_FEATURES,
        "masks": masks_summary,
        "acquisition": acquisition_summary,
        "conditions": all_conditions,
        "condition_count": len(all_conditions),
        "comparisons": comparisons,
        "payloads": payloads,
        "protocol": {
            "final_labels_scope": "evaluator only",
            "target_order": "label blind nested prefix",
            "raw_masking": "before frozen transformation",
            "version": config.protocol_id,
        },
    }

    experiment_id = stable_hash(deterministic)[:24]
    root = config.artifact_root / experiment_id
    payloads_dir = root / "payloads"

    content_hashes = {
        "config": write_json_artifact(root, "config.json", config.to_dict()),
        "seeds": write_json_artifact(root, "seeds.json", deterministic["seeds"]),
        "masks": write_json_artifact(root, "masks.json", masks_summary),
        "acquisition": write_json_artifact(root, "acquisition.json", acquisition_summary),
        "conditions": write_json_artifact(root, "conditions.json", all_conditions),
        "comparisons": write_json_artifact(root, "comparisons.json", comparisons),
        "budget_curve": write_json_artifact(payloads_dir, "budget_curve.json", payload_budget_curve),
        "pattern_vs_rate": write_json_artifact(payloads_dir, "pattern_vs_rate.json", payload_pattern_vs_rate),
        "reliability": write_json_artifact(payloads_dir, "reliability.json", payload_reliability),
        "decision_loss": write_json_artifact(payloads_dir, "decision_loss.json", payload_decision_loss),
        "logical_content": stable_hash(deterministic),
    }

    execution_id = str(uuid4())
    repository = ExperimentRepository.from_url(database_url)
    try:
        repository.put(
            experiment_id,
            deterministic,
            content_hashes,
            execution_id,
            {"execution_id": execution_id, "provenance": audit_provenance()},
        )
    finally:
        repository.dispose()

    return StressResult(
        experiment_id=experiment_id,
        execution_id=execution_id,
        conditions=all_conditions,
        comparisons=comparisons,
        payloads=payloads,
        content_hashes=content_hashes,
    )


def run_stress_engine(dataset: BankDataset, config: StressConfig, database_url: str) -> StressResult:
    """Run stress engine: prepare partitions and execute under strict boundary rules."""
    partitions, evaluator = prepare_stress_partitions(dataset, config)
    return execute_stress_engine(partitions, config, evaluator, database_url)
