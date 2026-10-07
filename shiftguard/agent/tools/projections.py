"""Strict, allowlisted projections for every provider-visible tool result."""

from __future__ import annotations

import math
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from shiftguard.agent.policy import APPROVED_CALIBRATORS, APPROVED_PREDICTORS, APPROVED_SCENARIOS, safe_tool_call_id
from shiftguard.agent.schemas import PUBLIC_ERROR_MESSAGES, PublicToolError, ToolResult, sanitize_error_input


class ProjectionModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class MetricsProjection(ProjectionModel):
    brier_score: float | int | None = None
    log_loss: float | int | None = None
    ece: float | int | None = None


class SparseDiagnosticsProjection(ProjectionModel):
    affected_fallback_rows: int | None = Field(default=None, ge=0)
    resolution_counts: dict[str, int] = Field(default_factory=dict)
    bin_eval_counts: dict[str, int] = Field(default_factory=dict)
    bin_fallback_counts: dict[str, int] = Field(default_factory=dict)
    bin_support: dict[str, int] = Field(default_factory=dict)
    bin_resolution_counts: dict[str, dict[str, int]] = Field(default_factory=dict)
    bin_resolved_maps: dict[str, str] = Field(default_factory=dict)
    sparse_prediction_failures: int | None = Field(default=None, ge=0)


class ConditionProjection(ProjectionModel):
    condition_id: str | None = None
    predictor: str | None = None
    scenario: str | None = None
    budget: int | None = Field(default=None, ge=0, le=200)
    method: str | None = None
    resolved_method: str | None = None
    status: str | None = None
    fit_status: str | None = None
    fallback_reason: str | None = None
    fallback_chain: list[str] = Field(default_factory=list, max_length=16)
    labels_consumed: int | None = Field(default=None, ge=0)
    prediction_failed: bool = False
    metrics: MetricsProjection | None = None
    sparse_bin_diagnostics: SparseDiagnosticsProjection | None = None


_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_KEY = re.compile(r"^[a-z0-9_]{1,128}$")
_SHA = re.compile(r"^[a-f0-9]{64}$")
_TOOL_NAMES = frozenset({
    "calculate_decision_loss", "compare_calibrators", "compare_outages", "generate_result_summary",
    "get_experiment_metadata", "get_label_budget_curve", "inspect_dataset", "inspect_missingness",
    "list_available_scenarios", "read_experiment_results", "run_experiment", "run_stress_suite",
})
_METHODS = frozenset(APPROVED_CALIBRATORS) | frozenset({"fitted_bin_temperature"})
_BIN_RESOLUTION_STATES = frozenset({"mixed", "empty"})
_OUTAGE_CONDITION_KEYS = frozenset({"no_outage_raw", "no_outage_source_temperature", "outage_raw", "outage_source_temperature", "outage_target_temperature"})
_SAFE_ERROR_MESSAGES = PUBLIC_ERROR_MESSAGES


def _token(value: Any) -> str | None:
    return value if isinstance(value, str) and _TOKEN.fullmatch(value) else None


def _experiment_id(value: Any) -> str | None:
    return value if isinstance(value, str) and re.fullmatch(r"[a-f0-9]{24}", value) else None


def _condition_id(value: Any) -> str | None:
    return _experiment_id(value)


def _identity_hash(value: Any) -> str | None:
    return value if isinstance(value, str) and _SHA.fullmatch(value) else None


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        return None
    return value


def _count(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _condition_key(value: Any) -> bool:
    if not isinstance(value, str) or len(value) > 128:
        return False
    if value in _OUTAGE_CONDITION_KEYS:
        return True
    parts = value.split("__")
    if len(parts) != 4:
        return False
    predictor, scenario, budget_part, method = parts
    try:
        budget = int(budget_part.removeprefix("b")) if budget_part.startswith("b") else -1
    except ValueError:
        return False
    return predictor in APPROVED_PREDICTORS and (scenario in APPROVED_SCENARIOS or scenario == "mcar_matched_history") and budget in {0, 25, 50, 100, 200} and method in APPROVED_CALIBRATORS


def _metrics(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    values = {key: _number(raw.get(key)) for key in ("brier_score", "log_loss", "ece") if key in raw}
    try:
        return MetricsProjection.model_validate(values).model_dump(mode="json", exclude_unset=True)
    except ValidationError:
        return None


def _sparse(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    value: dict[str, Any] = {}
    for key in ("affected_fallback_rows", "sparse_prediction_failures"):
        count = _count(raw.get(key))
        if key in raw and count is not None:
            value[key] = count
    counts = raw.get("resolution_counts")
    value["resolution_counts"] = {
        method: count for method, item in counts.items()
        if isinstance(counts, dict) and method in _METHODS and (count := _count(item)) is not None
    } if isinstance(counts, dict) else {}
    for key in ("bin_eval_counts", "bin_fallback_counts", "bin_support"):
        mapping = raw.get(key)
        value[key] = {
            str(bin_id): count for bin_id, item in mapping.items()
            if isinstance(mapping, dict) and str(bin_id).isdigit() and 0 <= int(bin_id) <= 9
            and (count := _count(item)) is not None
        } if isinstance(mapping, dict) else {}
    nested = raw.get("bin_resolution_counts")
    value["bin_resolution_counts"] = {
        str(bin_id): {method: count for method, item in methods.items()
                      if method in _METHODS and (count := _count(item)) is not None}
        for bin_id, methods in nested.items()
        if isinstance(nested, dict) and str(bin_id).isdigit() and 0 <= int(bin_id) <= 9 and isinstance(methods, dict)
    } if isinstance(nested, dict) else {}
    maps = raw.get("bin_resolved_maps")
    value["bin_resolved_maps"] = {
        str(bin_id): method for bin_id, method in maps.items()
        if isinstance(maps, dict) and str(bin_id).isdigit() and 0 <= int(bin_id) <= 9
        and method in _METHODS | _BIN_RESOLUTION_STATES
    } if isinstance(maps, dict) else {}
    try:
        return SparseDiagnosticsProjection.model_validate(value).model_dump(mode="json", exclude_none=True)
    except ValidationError:
        return None


def _condition(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    predictor = raw.get("predictor")
    scenario = raw.get("scenario")
    method = raw.get("method")
    resolved = raw.get("resolved_method")
    status = raw.get("status")
    fit_status = raw.get("fit_status")
    projected = {
        "condition_id": _condition_id(raw.get("condition_id")),
        "predictor": predictor if predictor in APPROVED_PREDICTORS else None,
        "scenario": scenario if scenario in APPROVED_SCENARIOS or scenario == "mcar_matched_history" else None,
        "budget": raw.get("budget") if type(raw.get("budget")) is int and raw.get("budget") in {0, 25, 50, 100, 200} else None,
        "method": method if method in _METHODS else None,
        "resolved_method": resolved if resolved in _METHODS else None,
        "status": status if status in {"scored", "failed", "unavailable", "cancelled"} else None,
        "fit_status": fit_status if fit_status in {"fitted", "failed", "not_applicable", "not_attempted", "fallback"} else None,
        "fallback_reason": _token(raw.get("fallback_reason")),
        "fallback_chain": [method for method in raw.get("fallback_chain", []) if method in _METHODS][:16]
        if isinstance(raw.get("fallback_chain"), list) else [],
        "labels_consumed": _count(raw.get("labels_consumed")),
        "prediction_failed": raw.get("prediction_failed") is True,
        "metrics": _metrics(raw.get("metrics")),
        "sparse_bin_diagnostics": _sparse(raw.get("sparse_bin_diagnostics")),
    }
    try:
        serialized = ConditionProjection.model_validate(projected).model_dump(mode="json", exclude_unset=True)
        return {key: value for key, value in serialized.items() if value is not None}
    except ValidationError:
        return None


def _project_metadata(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "experiment_id": _experiment_id(data.get("experiment_id")),
        "generation_id": _token(data.get("generation_id")),
        "execution_id": _token(data.get("execution_id")),
        "published_at": data.get("published_at") if isinstance(data.get("published_at"), str) and len(data["published_at"]) <= 64 else None,
        "condition_count": _count(data.get("condition_count")),
    }
    for key in ("dataset", "config", "seeds", "protocol"):
        item = data.get(key)
        out[key] = item if isinstance(item, dict) else {}
    out["content_hashes"] = {
        key: value for key, value in (data.get("content_hashes") or {}).items()
        if isinstance(key, str) and _KEY.fullmatch(key) and isinstance(value, str) and _SHA.fullmatch(value)
    } if isinstance(data.get("content_hashes"), dict) else {}
    config = out["config"]
    safe_config: dict[str, Any] = {}
    if config.get("master_seed") == 31001:
        safe_config["master_seed"] = 31001
    expected_features = ["age", "job", "marital", "education", "default", "housing", "loan", "pdays", "previous", "poutcome"]
    if config.get("features") == expected_features:
        safe_config["features"] = expected_features
    expected_fractions = {"train": 0.55, "source_cal": 0.15, "pool": 0.10, "final": 0.20}
    if config.get("role_fractions") == expected_fractions:
        safe_config["role_fractions"] = expected_fractions
    if config.get("protocol_id") in {"sg-protocol-1.0-draft", "sg-protocol-1.0-draft-gate3"}:
        safe_config["protocol_id"] = config["protocol_id"]
    if config.get("evaluation_tier") == "development":
        safe_config["evaluation_tier"] = "development"
    out["config"] = safe_config
    dataset = out["dataset"]
    out["dataset"] = {key: value for key, value in dataset.items()
                      if key in {"raw_hash", "clean_hash"} and isinstance(value, str) and _SHA.fullmatch(value)}
    out["seeds"] = {"master_seed": 31001} if data.get("seeds") == {"master_seed": 31001} else {}
    protocol_id = out["config"].get("protocol_id")
    out["protocol"] = {"protocol_id": protocol_id} if isinstance(protocol_id, str) and _TOKEN.fullmatch(protocol_id) else {}
    return {key: value for key, value in out.items() if value is not None}


def _project_data(name: str, data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    if name == "get_experiment_metadata":
        return _project_metadata(data)
    if name == "read_experiment_results":
        out = {key: data[key] for key in ("experiment_id", "published_at", "total_conditions") if key in data}
        out["experiment_id"] = _experiment_id(out.get("experiment_id"))
        out["total_conditions"] = _count(out.get("total_conditions"))
        if not isinstance(out.get("published_at"), str) or len(out["published_at"]) > 64:
            out.pop("published_at", None)
        if "condition_key" in data:
            out["condition_key"] = data["condition_key"] if _condition_key(data["condition_key"]) else None
            condition = {
                key: data[key] for key in (
                    "condition_id", "predictor", "scenario", "budget", "method", "resolved_method", "status",
                    "fit_status", "fallback_reason", "fallback_chain", "labels_consumed", "prediction_failed",
                    "metrics", "sparse_bin_diagnostics",
                ) if key in data
            }
            condition.setdefault("metrics", data.get("metrics"))
            condition.setdefault("sparse_bin_diagnostics", data.get("sparse_bin_diagnostics"))
            out.update(_condition(condition) or {})
        else:
            conditions = data.get("conditions")
            out["conditions"] = {
                key: projection for key, value in conditions.items()
                if _condition_key(key) and (projection := _condition(value)) is not None
            } if isinstance(conditions, dict) else {}
        return {key: value for key, value in out.items() if value is not None}
    if name == "compare_calibrators":
        comparisons = data.get("calibrator_comparisons")
        projected = {}
        if isinstance(comparisons, dict):
            for method, raw in comparisons.items():
                if method not in _METHODS or not isinstance(raw, dict):
                    continue
                projected[method] = {
                    "condition_id": _condition_id(raw.get("condition_id")),
                    "predictor_id": _identity_hash(raw.get("predictor_id")),
                    "dataset_id": _identity_hash(raw.get("dataset_id")),
                    "evaluation_rows_id": _identity_hash(raw.get("evaluation_rows_id")),
                    "source_map_id": _identity_hash(raw.get("source_map_id")),
                    "scenario": raw.get("scenario") if raw.get("scenario") in APPROVED_SCENARIOS else None,
                    "budget": raw.get("budget") if type(raw.get("budget")) is int and raw.get("budget") in {0, 25, 50, 100, 200} else None,
                    "resolved_method": raw.get("resolved_method") if raw.get("resolved_method") in _METHODS else None,
                    "fit_status": raw.get("fit_status") if raw.get("fit_status") in {"fitted", "failed", "not_applicable", "not_attempted", "fallback"} else None,
                    "fallback_reason": _token(raw.get("fallback_reason")),
                    "comparison_qualified": raw.get("comparison_qualified") is True,
                    "qualification_reason": _token(raw.get("qualification_reason")),
                    "status": raw.get("status") if raw.get("status") in {"scored", "failed", "unavailable", "cancelled"} else "unavailable",
                    "brier_score": _number(raw.get("brier_score")),
                    "log_loss": _number(raw.get("log_loss")),
                    "ece": _number(raw.get("ece")),
                    "sparse_bin_diagnostics": _sparse(raw.get("sparse_bin_diagnostics")),
                }
        return {"experiment_id": _experiment_id(data.get("experiment_id")), "predictor": data.get("predictor") if data.get("predictor") in APPROVED_PREDICTORS else None,
                "scenario": data.get("scenario") if data.get("scenario") in APPROVED_SCENARIOS else None,
                "budget": data.get("budget") if type(data.get("budget")) is int and data.get("budget") in {0, 25, 50, 100, 200} else None,
                "calibrator_comparisons": projected}
    if name == "compare_outages":
        comp = data.get("comparison") if isinstance(data.get("comparison"), dict) else {}
        methods = comp.get("methods") if isinstance(comp.get("methods"), dict) else {}
        projected_methods = {}
        for method, item in methods.items():
            if method not in _METHODS or not isinstance(item, dict):
                continue
            projected_methods[method] = {
                key: (_condition_id(item.get(key)) if key.endswith("condition_id") else _number(item.get(key)))
                for key in ("block_condition_id", "cellwise_condition_id", "block_brier", "cellwise_brier", "delta_brier", "block_log_loss", "cellwise_log_loss", "residual_mismatch")
                if item.get(key) is not None
            }
            projected_methods[method].update({
                "available": item.get("available") is True,
                "comparison_qualified": item.get("comparison_qualified") is True,
                "qualification_reason": _token(item.get("qualification_reason")),
            })
        return {"experiment_id": _experiment_id(data.get("experiment_id")),
                "predictor": data.get("predictor") if data.get("predictor") in APPROVED_PREDICTORS else None,
                "comparison": {"block_scenario": "history_block_0_50", "cellwise_scenario": "mcar_matched_history",
                               "budget": comp.get("budget") if type(comp.get("budget")) is int and comp.get("budget") in {0, 25, 50, 100, 200} else None,
                               "methods": projected_methods}}
    if name == "get_label_budget_curve":
        points = []
        for point in data.get("points", []) if isinstance(data.get("points"), list) else []:
            if not isinstance(point, dict):
                continue
            points.append({
                "condition_id": _condition_id(point.get("condition_id")), "budget": point.get("budget") if type(point.get("budget")) is int and point.get("budget") in {0, 25, 50, 100, 200} else None,
                "labels_consumed": _count(point.get("labels_consumed")), "requested_method": point.get("requested_method") if point.get("requested_method") in _METHODS else None,
                "resolved_method": point.get("resolved_method") if point.get("resolved_method") in _METHODS else None,
                "status": point.get("status") if point.get("status") in {"scored", "failed", "unavailable", "cancelled"} else "unavailable",
                "available": point.get("available") is True, "metric_name": point.get("metric_name") if point.get("metric_name") in {"brier_score", "log_loss"} else None,
                "metric_value": _number(point.get("metric_value")), "unavailable_reason": _token(point.get("unavailable_reason")),
            })
        return {"experiment_id": _experiment_id(data.get("experiment_id")), "predictor": data.get("predictor") if data.get("predictor") in APPROVED_PREDICTORS else None,
                "scenario": data.get("scenario") if data.get("scenario") in APPROVED_SCENARIOS else None,
                "method": data.get("method") if data.get("method") in _METHODS else None,
                "metric": data.get("metric") if data.get("metric") in {"brier_score", "log_loss"} else None, "points": points}
    if name == "calculate_decision_loss":
        fields = ("experiment_id", "condition_id", "predictor", "scenario", "method", "budget", "fp_cost", "fn_cost", "threshold", "loss", "fp_count", "fn_count", "tp_count", "tn_count", "n_samples", "unavailable_reason")
        out = {key: data[key] for key in fields if key in data}
        for key in ("experiment_id", "condition_id"):
            if key in out:
                out[key] = _experiment_id(out[key]) if key == "experiment_id" else _condition_id(out[key])
        for key in ("fp_cost", "fn_cost", "threshold", "loss"):
            if key in out:
                out[key] = _number(out[key])
        for key in ("fp_count", "fn_count", "tp_count", "tn_count", "n_samples", "budget"):
            if key in out:
                out[key] = _count(out[key])
        if out.get("predictor") not in APPROVED_PREDICTORS: out["predictor"] = None
        if out.get("scenario") not in APPROVED_SCENARIOS: out["scenario"] = None
        if out.get("method") not in _METHODS: out["method"] = None
        if "unavailable_reason" in out: out["unavailable_reason"] = _token(out["unavailable_reason"])
        return {key: value for key, value in out.items() if value is not None}
    if name == "generate_result_summary":
        failed = []
        for item in data.get("failed_conditions", []) if isinstance(data.get("failed_conditions"), list) else []:
            if isinstance(item, dict) and _condition_key(item.get("condition_key")):
                failed.append({"condition_key": item["condition_key"], "condition_id": _condition_id(item.get("condition_id")),
                               "status": item.get("status") if item.get("status") in {"failed", "cancelled", "unavailable"} else "unavailable",
                               "requested_method": item.get("requested_method") if item.get("requested_method") in _METHODS else None,
                               "resolved_method": item.get("resolved_method") if item.get("resolved_method") in _METHODS else None,
                               "reason": _token(item.get("reason"))})
        sparse = {}
        raw_sparse = data.get("sparse_diagnostics_by_condition")
        if isinstance(raw_sparse, dict):
            for key, item in raw_sparse.items():
                if _condition_key(key) and isinstance(item, dict):
                    sparse[key] = {"condition_id": _condition_id(item.get("condition_id")),
                                   "requested_method": item.get("requested_method") if item.get("requested_method") in _METHODS else None,
                                   "resolved_method": item.get("resolved_method") if item.get("resolved_method") in _METHODS else None,
                                   "fallback_reason": _token(item.get("fallback_reason")),
                                   "sparse_bin_diagnostics": _sparse(item.get("sparse_bin_diagnostics"))}
        best = data.get("best_brier_condition")
        if isinstance(best, dict):
            best = {"condition_key": best.get("condition_key") if _condition_key(best.get("condition_key")) else None,
                    "condition_id": _condition_id(best.get("condition_id")), "predictor": best.get("predictor") if best.get("predictor") in APPROVED_PREDICTORS else None,
                    "scenario": best.get("scenario") if best.get("scenario") in APPROVED_SCENARIOS else None,
                    "method": best.get("method") if best.get("method") in _METHODS else None, "brier_score": _number(best.get("brier_score"))}
        else:
            best = None
        return {"experiment_id": _experiment_id(data.get("experiment_id")), "focus": data.get("focus") if data.get("focus") in {"all", "fallback", "outages", "calibration"} else None,
                "total_conditions": _count(data.get("total_conditions")), "scored_conditions": _count(data.get("scored_conditions")),
                "failed_conditions": failed, "whole_condition_fallbacks": _count(data.get("whole_condition_fallbacks")),
                "sparse_bin_fallback_conditions": _count(data.get("sparse_bin_fallback_conditions")),
                "total_affected_fallback_rows": _count(data.get("total_affected_fallback_rows")),
                "sparse_diagnostics_by_condition": sparse, "best_brier_condition": best,
                "pattern_comparisons_present": data.get("pattern_comparisons_present") is True}
    # Fixed metadata and run tools have explicit top-level contracts. Nested arbitrary values are omitted.
    static_fields = {
        "inspect_dataset": {"dataset_id", "name", "row_count", "modeled_features", "target_column", "natural_missingness_rate", "clean_sha256", "source_citation", "license", "evaluation_tier", "notes"},
        "list_available_scenarios": {"dataset_id", "approved_presets", "approved_scenarios", "supported_predictors", "supported_budgets", "supported_cost_pairs", "master_seed", "protocol_id"},
        "inspect_missingness": {"scenario", "pattern", "requested_cell_rate", "row_probability", "affected_features", "experiment_id", "created_at", "realized_mask_summaries", "notes"},
        "run_experiment": {"job_id", "status", "preset_name", "master_seed", "created_at", "notes"},
        "run_stress_suite": {"job_id", "status", "suite_name", "mapped_preset", "master_seed", "created_at", "notes"},
    }
    if name not in static_fields:
        return None
    out = {key: data[key] for key in static_fields[name] if key in data}
    if name in {"run_experiment", "run_stress_suite"}:
        job_id = _token(out.get("job_id"))
        status = out.get("status") if out.get("status") in {"queued", "running", "completed", "failed", "cancelled"} else None
        created_at = out.get("created_at")
        if not isinstance(created_at, str) or len(created_at) > 64 or not re.fullmatch(r"[0-9T:.+Z-]+", created_at):
            created_at = None
        if name == "run_experiment":
            preset = out.get("preset_name") if out.get("preset_name") in {"bank-baseline", "bank-stress", "bank-outage-50"} else None
            if job_id is None or status is None or preset is None:
                return None
            return {"job_id": job_id, "status": status, "preset_name": preset,
                    "master_seed": 31001 if out.get("master_seed") == 31001 else None,
                    "created_at": created_at,
                    "notes": f"Job {job_id} enqueued for preset '{preset}'. Controller will wait for durable worker execution."}
        suite = out.get("suite_name") if out.get("suite_name") in {"bank-stress", "bank-stress-30", "flagship-stress"} else None
        if job_id is None or status is None or suite is None or out.get("mapped_preset") != "bank-stress":
            return None
        return {"job_id": job_id, "status": status, "suite_name": suite, "mapped_preset": "bank-stress",
                "master_seed": 31001 if out.get("master_seed") == 31001 else None,
                "created_at": created_at,
                "notes": f"Stress suite mapped to preset 'bank-stress' (Job {job_id}). Controller will wait for durable worker execution."}
    if name == "list_available_scenarios":
        out["dataset_id"] = "bank" if out.get("dataset_id") == "bank" else None
        out["approved_presets"] = [item for item in out.get("approved_presets", []) if item in {"bank-baseline", "bank-stress", "bank-outage-50"}]
        allowed_scenarios = {"mcar_0_00", "mcar_0_10", "mcar_0_30", "history_block_0_50"}
        out["approved_scenarios"] = [
            {"id": item["id"], "type": item["type"], "rate": _number(item.get("rate")), "description": item["description"][:160]}
            for item in out.get("approved_scenarios", [])
            if isinstance(item, dict) and item.get("id") in allowed_scenarios
            and isinstance(item.get("type"), str) and isinstance(item.get("description"), str)
        ]
        out["supported_predictors"] = [item for item in out.get("supported_predictors", []) if item in APPROVED_PREDICTORS]
        out["supported_budgets"] = [item for item in out.get("supported_budgets", []) if type(item) is int and item in {0, 25, 50, 100, 200}]
        out["supported_cost_pairs"] = [
            pair for pair in out.get("supported_cost_pairs", [])
            if isinstance(pair, list) and len(pair) == 2 and tuple(pair) in {(1.0, 1.0), (1.0, 4.0), (4.0, 1.0), (1.0, 9.0), (9.0, 1.0)}
        ]
        out["master_seed"] = 31001 if out.get("master_seed") == 31001 else None
        if out.get("protocol_id") not in {"sg-protocol-1.0-draft", "sg-protocol-1.0-draft-gate3"}:
            out.pop("protocol_id", None)
        return {key: value for key, value in out.items() if value is not None}
    if name == "inspect_missingness" and "realized_mask_summaries" in out:
        from shiftguard.agent.tools.metadata import _project_masks
        out["realized_mask_summaries"] = _project_masks(out["realized_mask_summaries"])
        out["experiment_id"] = _experiment_id(out.get("experiment_id"))
        if out.get("scenario") not in APPROVED_SCENARIOS:
            out.pop("scenario", None)
    # These static outputs are constructed from source constants; restrict nested lists to scalar strings.
    for key, value in list(out.items()):
        if key == "realized_mask_summaries":
            # _project_masks has already applied the nested rate and identifier allowlists.
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            continue
        if isinstance(value, list):
            out[key] = [item for item in value if isinstance(item, (str, int, float, bool))][:256]
        elif isinstance(value, dict):
            out[key] = {k: v for k, v in value.items() if isinstance(k, str) and _KEY.fullmatch(k) and isinstance(v, (str, int, float, bool))}
        else:
            out.pop(key)
    return out


def sanitize_public_error(error: Any) -> str | dict[str, str] | None:
    """Preserve the public error shape while discarding raw messages and unknown fields."""
    return sanitize_error_input(error)


def sanitize_tool_error(error: Any) -> str | None:
    """Return a legacy string representation of the canonical public error."""
    if error is None or isinstance(error, str) and not error.strip():
        return None
    safe = sanitize_public_error(error)
    if isinstance(safe, dict):
        return f"{safe['code']}: {safe['message']}"
    return safe


def project_tool_result(result: ToolResult) -> ToolResult:
    """Apply the tool-specific allowlist at the final dispatch boundary."""
    if result.tool_name not in _TOOL_NAMES:
        result.tool_name = "unknown_tool"
    safe_call_id = safe_tool_call_id(result.tool_call_id)
    if safe_call_id is None:
        result.tool_call_id = "invalid_call_id"
    else:
        result.tool_call_id = safe_call_id
    result.job_id = _token(result.job_id)
    if result.data is not None:
        projected = _project_data(result.tool_name, result.data)
        if projected is None:
            return ToolResult(tool_name=result.tool_name, tool_call_id=result.tool_call_id,
                              status="unavailable", error="EXPERIMENT_UNAVAILABLE: Result did not satisfy the safe output contract.",
                              is_side_effect=result.is_side_effect, job_id=result.job_id)
        result.data = projected
    safe_error = sanitize_public_error(result.error)
    result.error = PublicToolError.model_validate(safe_error) if isinstance(safe_error, dict) else safe_error
    return result
