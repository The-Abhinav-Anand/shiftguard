"""Result tool handlers: read_experiment_results, get_experiment_metadata,
compare_calibrators, compare_outages, get_label_budget_curve,
calculate_decision_loss, generate_result_summary.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

from shiftguard.agent.policy import (
    APPROVED_CALIBRATORS,
    APPROVED_BUDGETS,
    APPROVED_METRICS,
    APPROVED_METHODS,
    APPROVED_PREDICTORS,
    APPROVED_SCENARIOS,
    BANK_MODELED_FEATURES,
    SUPPORTED_COST_PAIRS,
    AgentErrorCode,
)
from shiftguard.agent.schemas import (
    CalculateDecisionLossParams,
    CompareCalibratorsParams,
    CompareOutagesParams,
    GenerateResultSummaryParams,
    GetExperimentMetadataParams,
    GetLabelBudgetCurveParams,
    ReadExperimentResultsParams,
    ToolResult,
)
from shiftguard.agent.tools import ToolContext, experiment_evidence_allowed
from shiftguard.experiments.ids import stable_hash
from shiftguard.storage.repositories import ExperimentRepository

SPARSE_BIN_DIAGNOSTIC_KEYS = (
    "affected_fallback_rows",
    "resolution_counts",
    "bin_eval_counts",
    "bin_fallback_counts",
    "bin_support",
    "bin_resolution_counts",
    "bin_resolved_maps",
    "sparse_prediction_failures",
)
_SPARSE_MAP_NAMES = APPROVED_CALIBRATORS | frozenset({"fitted_bin_temperature"})
_SPARSE_BIN_STATES = frozenset({"mixed", "empty"})

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_OUTAGE_CONDITION_KEYS = frozenset({
    "no_outage_raw", "no_outage_source_temperature", "outage_raw",
    "outage_source_temperature", "outage_target_temperature",
})
_SAFE_REASON = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_CONDITION_ID = re.compile(r"^[a-f0-9]{24}$")


def _safe_id(value: Any) -> str | None:
    return value if isinstance(value, str) and _SAFE_ID.fullmatch(value) else None


def _safe_hash(value: Any) -> str | None:
    return value if isinstance(value, str) and _SHA256.fullmatch(value) else None


def _safe_condition_id(value: Any) -> str | None:
    return value if isinstance(value, str) and _CONDITION_ID.fullmatch(value) else None


def _safe_reason(value: Any) -> str | None:
    return value if isinstance(value, str) and _SAFE_REASON.fullmatch(value) else None


def _safe_number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(float(value)):
        return None
    return value


def _safe_count(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _is_safe_condition_key(value: Any) -> bool:
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
    return (
        predictor in APPROVED_PREDICTORS
        and (scenario in APPROVED_SCENARIOS or scenario == "mcar_matched_history")
        and budget in APPROVED_BUDGETS
        and method in APPROVED_CALIBRATORS
    )


def _project_metrics(raw: Any) -> dict[str, float | int | None] | None:
    if not isinstance(raw, dict):
        return None
    names = ("brier_score", "log_loss", "ece")
    return {name: _safe_number(raw.get(name)) for name in names if name in raw}


def _safe_bin_map(
    raw: Any, *, values_may_be_maps: bool = False, allow_bin_states: bool = False
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for key, value in raw.items():
        bin_key = str(key)
        if bin_key.isdigit() and 0 <= int(bin_key) <= 9:
            if values_may_be_maps:
                inner = {
                    str(method): count
                    for method, count in value.items()
                    if isinstance(value, dict)
                    and method in _SPARSE_MAP_NAMES
                    and _safe_count(count) is not None
                } if isinstance(value, dict) else {}
                out[bin_key] = inner
            elif isinstance(value, str) and (
                value in _SPARSE_MAP_NAMES or allow_bin_states and value in _SPARSE_BIN_STATES
            ):
                out[bin_key] = value
            elif _safe_count(value) is not None:
                out[bin_key] = value
    return out


def _project_sparse_bin_diagnostics(raw_diag: dict[str, Any] | None) -> dict[str, Any] | None:
    """Project the eight accepted diagnostic fields without forwarding nested source data."""
    if not raw_diag or not isinstance(raw_diag, dict):
        return None
    projected: dict[str, Any] = {}
    for key in ("affected_fallback_rows", "sparse_prediction_failures"):
        if key in raw_diag and _safe_count(raw_diag[key]) is not None:
            projected[key] = raw_diag[key]
    resolution_counts = raw_diag.get("resolution_counts")
    if isinstance(resolution_counts, dict):
        projected["resolution_counts"] = {
            method: _safe_count(count)
            for method, count in resolution_counts.items()
            if method in _SPARSE_MAP_NAMES and _safe_count(count) is not None
        }
    for key in ("bin_eval_counts", "bin_fallback_counts", "bin_support"):
        if key in raw_diag:
            projected[key] = _safe_bin_map(raw_diag[key])
    if "bin_resolution_counts" in raw_diag:
        projected["bin_resolution_counts"] = _safe_bin_map(raw_diag["bin_resolution_counts"], values_may_be_maps=True)
    if "bin_resolved_maps" in raw_diag:
        projected["bin_resolved_maps"] = _safe_bin_map(
            raw_diag["bin_resolved_maps"], allow_bin_states=True
        )
    return projected


def _get_payload(stored_exp: Any) -> dict[str, Any]:
    payload = getattr(stored_exp, "deterministic_payload", None)
    if payload is None:
        payload = getattr(stored_exp, "payload_json", {})
    return payload if isinstance(payload, dict) else {}


def _check_authorized(exp_id: str, ctx: ToolContext, tool_name: str, tool_call_id: str) -> ToolResult | None:
    if not experiment_evidence_allowed(ctx, exp_id):
        return ToolResult(
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            status="unavailable",
            error=f"{AgentErrorCode.UNAUTHORIZED_EXPERIMENT_REFERENCE}: Experiment reference is not authorized for this request.",
        )
    return None


def _project_condition(key: str, condition: Any) -> dict[str, Any] | None:
    if not _is_safe_condition_key(key) or not isinstance(condition, dict):
        return None
    predictor = condition.get("predictor") or condition.get("predictor_name")
    scenario = condition.get("scenario")
    method = condition.get("requested_method") or condition.get("method")
    resolved = condition.get("resolved_method")
    if predictor not in APPROVED_PREDICTORS:
        predictor = None
    if scenario not in APPROVED_SCENARIOS and scenario != "mcar_matched_history":
        scenario = None
    if method not in APPROVED_CALIBRATORS:
        method = None
    if resolved not in APPROVED_CALIBRATORS:
        resolved = None
    metrics = _project_metrics(condition.get("metrics"))
    result: dict[str, Any] = {
        "condition_id": _safe_condition_id(condition.get("condition_id")),
        "predictor": predictor,
        "scenario": scenario,
        "budget": condition.get("budget") if condition.get("budget") in APPROVED_BUDGETS else None,
        "method": method,
        "resolved_method": resolved,
        "status": condition.get("status") if condition.get("status") in {"scored", "failed", "unavailable", "cancelled"} else None,
        "fit_status": condition.get("fit_status") if condition.get("fit_status") in {"fitted", "failed", "not_applicable", "not_attempted", "fallback"} else None,
        "fallback_reason": _safe_reason(condition.get("fallback_reason")),
        "fallback_chain": [m for m in condition.get("fallback_chain", []) if m in APPROVED_CALIBRATORS][:16]
        if isinstance(condition.get("fallback_chain"), list) else [],
        "labels_consumed": _safe_count(condition.get("labels_consumed")),
        "prediction_failed": condition.get("status") == "failed" or condition.get("metrics") is None,
        "metrics": metrics,
        "sparse_bin_diagnostics": _project_sparse_bin_diagnostics(condition.get("sparse_bin_diagnostics")),
    }
    return result


_CONTEXT_REQUIRED = (
    "dataset_id",
    "predictor_id",
    "evaluation_rows_id",
    "source_map_id",
    "test_mask_id",
    "scenario",
    "budget",
    "acquired_record_ids",
    "fitted_parameters",
    "fit_status",
    "resolved_method",
)


def _comparison_context_reason(
    baseline: Any,
    candidate: Any,
    *,
    expected_scenario: str | tuple[str, str],
    expected_budget: int,
    expected_predictor: str | None = None,
    expected_methods: tuple[str, str] | None = None,
    compare_mask: bool = True,
) -> str | None:
    if not isinstance(baseline, dict) or not isinstance(candidate, dict):
        return "missing_comparison_context"
    if any(key not in baseline or key not in candidate for key in _CONTEXT_REQUIRED):
        return "missing_comparison_context"
    for key in ("dataset_id", "predictor_id", "evaluation_rows_id", "source_map_id"):
        left, right = _safe_hash(baseline.get(key)), _safe_hash(candidate.get(key))
        if left is None or right is None:
            return "missing_comparison_context"
        if left != right:
            return f"mismatched_{key}"
    if compare_mask and baseline.get("test_mask_id") != candidate.get("test_mask_id"):
        return "mismatched_test_mask_id"
    for condition in (baseline, candidate):
        if condition.get("test_mask_id") is not None and _safe_hash(condition.get("test_mask_id")) is None:
            return "missing_comparison_context"
    expected_left, expected_right = (expected_scenario, expected_scenario) if isinstance(expected_scenario, str) else expected_scenario
    if baseline.get("scenario") != expected_left or candidate.get("scenario") != expected_right:
        return "mismatched_scenario"
    if baseline.get("budget") != expected_budget or candidate.get("budget") != expected_budget:
        return "mismatched_budget"
    if baseline.get("acquired_record_ids") != candidate.get("acquired_record_ids"):
        return "mismatched_acquisition"
    if (not isinstance(baseline.get("acquired_record_ids"), list) or not isinstance(candidate.get("acquired_record_ids"), list)
            or any(type(row_id) is not int or row_id < 0 for row_id in baseline["acquired_record_ids"] + candidate["acquired_record_ids"])):
        return "missing_comparison_context"
    if baseline.get("fit_status") is None or candidate.get("fit_status") is None:
        return "missing_comparison_context"
    if baseline.get("resolved_method") not in APPROVED_CALIBRATORS or candidate.get("resolved_method") not in APPROVED_CALIBRATORS:
        return "missing_comparison_context"
    if not isinstance(baseline.get("fitted_parameters"), dict) or not isinstance(candidate.get("fitted_parameters"), dict):
        return "missing_comparison_context"
    for index, condition in enumerate((baseline, candidate)):
        predictor = condition.get("predictor_name", condition.get("predictor"))
        method = condition.get("requested_method") or condition.get("method")
        expected_method = expected_methods[index] if expected_methods else None
        if (predictor not in APPROVED_PREDICTORS or expected_predictor and predictor != expected_predictor
                or method not in APPROVED_CALIBRATORS or expected_method and method != expected_method):
            return "mismatched_predictor_or_method"
        if not _condition_digest_valid(condition):
            return "invalid_condition_identity"
        parameters = condition["fitted_parameters"]
        parameter_status = parameters.get("fit_status")
        if method == "raw":
            if parameter_status != "pipeline_direct" or parameters.get("type") != "raw_frozen_pipeline":
                return "unverified_fitted_parameters"
        elif parameter_status != condition.get("fit_status"):
            return "unverified_fitted_parameters"
    return None


def _condition_digest_valid(condition: dict[str, Any]) -> bool:
    condition_id = condition.get("condition_id")
    if not isinstance(condition_id, str) or not re.fullmatch(r"[a-f0-9]{24}", condition_id):
        return False
    content = {key: value for key, value in condition.items() if key != "condition_id"}
    try:
        return stable_hash(content)[:24] == condition_id
    except (TypeError, ValueError):
        return False


def read_experiment_results(
    params: ReadExperimentResultsParams, ctx: ToolContext, tool_call_id: str
) -> ToolResult:
    """Read published condition metrics, diagnostics, and sparse-bin fields from an experiment."""
    exp_id = params.experiment_id.strip()
    auth_err = _check_authorized(exp_id, ctx, "read_experiment_results", tool_call_id)
    if auth_err:
        return auth_err

    repo = ExperimentRepository(ctx.engine)
    published = repo.get_published(exp_id)
    if not published:
        return ToolResult(
            tool_name="read_experiment_results",
            tool_call_id=tool_call_id,
            status="error",
            error=f"Experiment '{exp_id}' not found among PUBLISHED records.",
        )

    stored_exp, pub_rec = published
    payload = _get_payload(stored_exp)
    conditions = payload.get("conditions", {})

    if params.condition_key:
        ck = params.condition_key.strip()
        if ck not in conditions:
            return ToolResult(
                tool_name="read_experiment_results",
                tool_call_id=tool_call_id,
                status="error",
                error=f"Condition '{ck}' not found in experiment '{exp_id}'. Exact condition key required.",
            )
        cond_data = _project_condition(ck, conditions[ck])
        if cond_data is None:
            return ToolResult(tool_name="read_experiment_results", tool_call_id=tool_call_id,
                              status="unavailable", error="Condition does not satisfy the safe result contract.")
        return ToolResult(
            tool_name="read_experiment_results",
            tool_call_id=tool_call_id,
            status="success",
            data={
                "experiment_id": exp_id,
                "condition_key": ck,
                **cond_data,
            },
        )

    # Return summary projection of all conditions
    summary_conditions = {}
    for k, v in conditions.items():
        projected = _project_condition(k, v)
        if projected is not None:
            summary_conditions[k] = projected

    return ToolResult(
        tool_name="read_experiment_results",
        tool_call_id=tool_call_id,
        status="success",
        data={
            "experiment_id": exp_id,
            "published_at": pub_rec.created_at,
            "total_conditions": len(conditions),
            "conditions": summary_conditions,
        },
    )


def get_experiment_metadata(
    params: GetExperimentMetadataParams, ctx: ToolContext, tool_call_id: str
) -> ToolResult:
    """Read experiment provenance, seeds, configuration, and content hashes."""
    exp_id = params.experiment_id.strip()
    auth_err = _check_authorized(exp_id, ctx, "get_experiment_metadata", tool_call_id)
    if auth_err:
        return auth_err
    repo = ExperimentRepository(ctx.engine)
    published = repo.get_published(exp_id)
    if not published:
        return ToolResult(
            tool_name="get_experiment_metadata",
            tool_call_id=tool_call_id,
            status="error",
            error=f"Experiment '{exp_id}' not found among PUBLISHED records.",
        )

    stored_exp, pub_rec = published
    payload = _get_payload(stored_exp)

    # Project only fixed protocol fields and scalar identity/hash values.
    raw_config = payload.get("config") or {}
    projected_config: dict[str, Any] = {}
    if isinstance(raw_config, dict):
        if raw_config.get("master_seed") == 31001:
            projected_config["master_seed"] = 31001
        if raw_config.get("features") == list(BANK_MODELED_FEATURES):
            projected_config["features"] = list(BANK_MODELED_FEATURES)
        if raw_config.get("protocol_id") in {"sg-protocol-1.0-draft", "sg-protocol-1.0-draft-gate3"}:
            projected_config["protocol_id"] = raw_config["protocol_id"]
        if raw_config.get("evaluation_tier") == "development":
            projected_config["evaluation_tier"] = "development"
        fractions = raw_config.get("role_fractions")
        expected_fractions = {"train": 0.55, "source_cal": 0.15, "pool": 0.10, "final": 0.20}
        if fractions == expected_fractions:
            projected_config["role_fractions"] = expected_fractions

    raw_hashes = getattr(stored_exp, "content_hashes", {})
    safe_hashes = {
        key: value for key, value in raw_hashes.items()
        if isinstance(key, str) and re.fullmatch(r"[a-z0-9_]{1,64}", key)
        and isinstance(value, str) and _SHA256.fullmatch(value)
    } if isinstance(raw_hashes, dict) else {}
    raw_dataset = payload.get("dataset") if isinstance(payload.get("dataset"), dict) else {}
    safe_dataset = {
        key: value for key, value in raw_dataset.items()
        if key in {"raw_hash", "clean_hash"} and isinstance(value, str) and _SHA256.fullmatch(value)
    }
    raw_seeds = payload.get("seeds") if isinstance(payload.get("seeds"), dict) else {}
    safe_seeds = {"master_seed": 31001} if raw_seeds.get("master") == 31001 or (isinstance(raw_config, dict) and raw_config.get("master_seed") == 31001) else {}

    return ToolResult(
        tool_name="get_experiment_metadata",
        tool_call_id=tool_call_id,
        status="success",
        data={
            "experiment_id": getattr(stored_exp, "experiment_id", getattr(stored_exp, "id", exp_id)),
            "generation_id": pub_rec.generation_id,
            "execution_id": getattr(pub_rec, "execution_id", ""),
            "published_at": pub_rec.created_at,
            "dataset": safe_dataset,
            "seeds": safe_seeds,
            "config": projected_config,
            "protocol": {"protocol_id": projected_config.get("protocol_id")} if projected_config.get("protocol_id") else {},
            "content_hashes": safe_hashes,
            "condition_count": _safe_count(payload.get("condition_count", len(payload.get("conditions", {})) if isinstance(payload.get("conditions"), dict) else 0)) or 0,
        },
    )


def compare_calibrators(
    params: CompareCalibratorsParams, ctx: ToolContext, tool_call_id: str
) -> ToolResult:
    """Compare calibration methods on a matching scenario, predictor, and label budget."""
    exp_id = params.experiment_id.strip()
    scen = params.scenario.strip().lower()
    pred = params.predictor.strip().lower()
    budget = params.budget

    auth_err = _check_authorized(exp_id, ctx, "compare_calibrators", tool_call_id)
    if auth_err:
        return auth_err
    if scen not in APPROVED_SCENARIOS or pred not in APPROVED_PREDICTORS or budget not in APPROVED_BUDGETS:
        return ToolResult(tool_name="compare_calibrators", tool_call_id=tool_call_id, status="error",
                          error=f"{AgentErrorCode.UNSUPPORTED_PARAMETER}: Unsupported scenario, predictor, or budget.")

    repo = ExperimentRepository(ctx.engine)
    published = repo.get_published(exp_id)
    if not published:
        return ToolResult(
            tool_name="compare_calibrators",
            tool_call_id=tool_call_id,
            status="error",
            error=f"Experiment '{exp_id}' not found among PUBLISHED records.",
        )

    stored_exp, pub_rec = published
    payload = _get_payload(stored_exp)
    conditions = payload.get("conditions", {})

    raw_cond = conditions.get(f"{pred}__{scen}__b{budget}__raw")
    method_results = {}
    for m in sorted(APPROVED_CALIBRATORS):
        cond_key = f"{pred}__{scen}__b{budget}__{m}"
        cond = conditions.get(cond_key)
        if cond:
            metrics = cond.get("metrics") or {}
            compat_reason = (
                "missing_comparison_context" if raw_cond is None else
                _comparison_context_reason(
                    raw_cond, cond, expected_scenario=scen, expected_budget=budget,
                    expected_predictor=pred, expected_methods=("raw", m),
                )
            )
            is_compat = compat_reason is None
            projected_metrics = _project_metrics(metrics)

            method_results[m] = {
                "condition_id": _safe_condition_id(cond.get("condition_id")),
                "predictor_id": _safe_hash(cond.get("predictor_id")),
                "dataset_id": _safe_hash(cond.get("dataset_id")),
                "evaluation_rows_id": _safe_hash(cond.get("evaluation_rows_id")),
                "source_map_id": _safe_hash(cond.get("source_map_id")),
                "scenario": cond.get("scenario") if cond.get("scenario") in APPROVED_SCENARIOS else None,
                "budget": cond.get("budget") if cond.get("budget") in APPROVED_BUDGETS else None,
                "resolved_method": cond.get("resolved_method") if cond.get("resolved_method") in APPROVED_CALIBRATORS else None,
                "fit_status": cond.get("fit_status") if cond.get("fit_status") in {"fitted", "failed", "not_applicable", "not_attempted", "fallback"} else None,
                "fallback_reason": _safe_reason(cond.get("fallback_reason")),
                "comparison_qualified": is_compat,
                "qualification_reason": compat_reason,
                "status": cond.get("status") if cond.get("status") in {"scored", "failed", "unavailable", "cancelled"} else "unavailable",
                "brier_score": projected_metrics.get("brier_score") if projected_metrics else None,
                "log_loss": projected_metrics.get("log_loss") if projected_metrics else None,
                "ece": projected_metrics.get("ece") if projected_metrics else None,
                "sparse_bin_diagnostics": _project_sparse_bin_diagnostics(cond.get("sparse_bin_diagnostics")),
            }

    if not method_results:
        return ToolResult(
            tool_name="compare_calibrators",
            tool_call_id=tool_call_id,
            status="unavailable",
            error=f"No matching conditions found for predictor '{pred}', scenario '{scen}', budget {budget} in experiment '{exp_id}'.",
        )

    return ToolResult(
        tool_name="compare_calibrators",
        tool_call_id=tool_call_id,
        status="success",
        data={
            "experiment_id": exp_id,
            "predictor": pred,
            "scenario": scen,
            "budget": budget,
            "calibrator_comparisons": method_results,
            "notes": "Single-seed (31001) comparison. Differences reflect illustrative sample performance.",
        },
    )


def compare_outages(
    params: CompareOutagesParams, ctx: ToolContext, tool_call_id: str
) -> ToolResult:
    """Read persisted paired pattern comparison (block outage vs matched MCAR) at evaluation budget."""
    exp_id = params.experiment_id.strip()
    pred = params.predictor.strip().lower()
    budget = params.budget

    auth_err = _check_authorized(exp_id, ctx, "compare_outages", tool_call_id)
    if auth_err:
        return auth_err
    if pred not in APPROVED_PREDICTORS or budget not in APPROVED_BUDGETS:
        return ToolResult(tool_name="compare_outages", tool_call_id=tool_call_id, status="error",
                          error=f"{AgentErrorCode.UNSUPPORTED_PARAMETER}: Unsupported predictor or budget.")

    repo = ExperimentRepository(ctx.engine)
    published = repo.get_published(exp_id)
    if not published:
        return ToolResult(
            tool_name="compare_outages",
            tool_call_id=tool_call_id,
            status="error",
            error=f"Experiment '{exp_id}' not found among PUBLISHED records.",
        )

    stored_exp, pub_rec = published
    payload = _get_payload(stored_exp)
    comparisons = payload.get("comparisons", {}).get("pattern_comparison", {})
    pred_comp = comparisons.get(pred)

    if not pred_comp:
        # Fallback to payloads/pattern_vs_rate
        p_vs_r = payload.get("payloads", {}).get("pattern_vs_rate", {}).get("comparisons", {})
        pred_comp = p_vs_r.get(pred)

    if not pred_comp:
        return ToolResult(
            tool_name="compare_outages",
            tool_call_id=tool_call_id,
            status="unavailable",
            error=f"No pattern-vs-rate outage comparison found for predictor '{pred}' in experiment '{exp_id}'.",
        )

    if pred_comp.get("budget") != budget:
        return ToolResult(
            tool_name="compare_outages",
            tool_call_id=tool_call_id,
            status="unavailable",
            error=f"No pattern comparison found for predictor '{pred}' at budget {budget} in experiment '{exp_id}'. Persisted comparison is at budget {pred_comp.get('budget')}.",
        )

    conditions = payload.get("conditions", {})
    projected_methods: dict[str, Any] = {}
    raw_methods = pred_comp.get("methods", {})
    if isinstance(raw_methods, dict):
        for method in sorted(APPROVED_CALIBRATORS):
            item = raw_methods.get(method)
            if not isinstance(item, dict):
                continue
            block_id = _safe_condition_id(item.get("block_condition_id"))
            cell_id = _safe_condition_id(item.get("cellwise_condition_id"))
            block_cond = next((c for c in conditions.values() if isinstance(c, dict) and c.get("condition_id") == block_id), None)
            cell_cond = next((c for c in conditions.values() if isinstance(c, dict) and c.get("condition_id") == cell_id), None)
            context_reason = _comparison_context_reason(
                block_cond, cell_cond,
                expected_scenario=("history_block_0_50", "mcar_matched_history"),
                expected_budget=budget,
                expected_predictor=pred,
                expected_methods=(method, method),
                compare_mask=False,
            )
            if context_reason is None:
                for cond in (block_cond, cell_cond):
                    if cond.get("predictor_name", cond.get("predictor")) != pred or not _safe_hash(cond.get("test_mask_id")):
                        context_reason = "missing_comparison_context"
                        break
            block_metrics = _project_metrics(block_cond.get("metrics")) if isinstance(block_cond, dict) else None
            cell_metrics = _project_metrics(cell_cond.get("metrics")) if isinstance(cell_cond, dict) else None
            block_brier = block_metrics.get("brier_score") if block_metrics else None
            cell_brier = cell_metrics.get("brier_score") if cell_metrics else None
            available = block_brier is not None and cell_brier is not None
            qualified = context_reason is None and item.get("comparison_qualified") is True and available
            projected_methods[method] = {
                "available": available,
                "comparison_qualified": qualified,
                "qualification_reason": context_reason or _safe_reason(item.get("qualification_reason")),
                "block_condition_id": block_id,
                "cellwise_condition_id": cell_id,
                "block_brier": block_brier,
                "cellwise_brier": cell_brier,
                "delta_brier": float(block_brier) - float(cell_brier) if available else None,
                "block_log_loss": block_metrics.get("log_loss") if block_metrics else None,
                "cellwise_log_loss": cell_metrics.get("log_loss") if cell_metrics else None,
                "residual_mismatch": _safe_number(item.get("residual_mismatch")),
            }

    return ToolResult(
        tool_name="compare_outages",
        tool_call_id=tool_call_id,
        status="success",
        data={
            "experiment_id": exp_id,
            "predictor": pred,
            "comparison": {
                "block_scenario": "history_block_0_50",
                "cellwise_scenario": "mcar_matched_history",
                "budget": budget,
                "methods": projected_methods,
            },
            "notes": "Pattern comparison assesses structured block outage against rate-matched cellwise MCAR.",
        },
    )


def get_label_budget_curve(
    params: GetLabelBudgetCurveParams, ctx: ToolContext, tool_call_id: str
) -> ToolResult:
    """Read persisted label budget curve across budgets (0, 25, 50, 100, 200)."""
    exp_id = params.experiment_id.strip()
    scen = params.scenario.strip().lower()
    pred = params.predictor.strip().lower()
    method = params.method.strip().lower()
    metric = params.metric.strip().lower()

    auth_err = _check_authorized(exp_id, ctx, "get_label_budget_curve", tool_call_id)
    if auth_err:
        return auth_err
    if (scen not in APPROVED_SCENARIOS or pred not in APPROVED_PREDICTORS
            or method not in APPROVED_METHODS or metric not in APPROVED_METRICS):
        return ToolResult(tool_name="get_label_budget_curve", tool_call_id=tool_call_id, status="error",
                          error=f"{AgentErrorCode.UNSUPPORTED_PARAMETER}: Unsupported scenario, predictor, method, or metric.")

    repo = ExperimentRepository(ctx.engine)
    published = repo.get_published(exp_id)
    if not published:
        return ToolResult(
            tool_name="get_label_budget_curve",
            tool_call_id=tool_call_id,
            status="error",
            error=f"Experiment '{exp_id}' not found among PUBLISHED records.",
        )

    stored_exp, pub_rec = published
    payload = _get_payload(stored_exp)
    budget_curve_payload = payload.get("payloads", {}).get("budget_curve", {})
    scenarios = budget_curve_payload.get("scenarios", {})
    key = f"{pred}__{scen}"
    scen_curve = scenarios.get(key, {})
    method_points = scen_curve.get(method)

    if not method_points:
        return ToolResult(
            tool_name="get_label_budget_curve",
            tool_call_id=tool_call_id,
            status="unavailable",
            error=f"No budget curve data for predictor '{pred}', scenario '{scen}', method '{method}' in experiment '{exp_id}'.",
        )

    points = []
    for pt in method_points:
        b = pt.get("budget")
        if type(b) is not int or b not in APPROVED_BUDGETS:
            continue
        c_key = f"{pred}__{scen}__b{b}__{method}"
        cond_data = payload.get("conditions", {}).get(c_key)
        cond_id = _safe_condition_id(cond_data.get("condition_id")) if isinstance(cond_data, dict) else None
        bound = bool(
            isinstance(cond_data, dict)
            and cond_id
            and pt.get("condition_id") == cond_id
            and cond_data.get("scenario") == scen
            and cond_data.get("predictor_name", cond_data.get("predictor")) == pred
            and cond_data.get("budget") == b
            and (cond_data.get("requested_method") or cond_data.get("method")) == method
            and all(key in cond_data for key in ("dataset_id", "predictor_id", "evaluation_rows_id", "test_mask_id", "source_map_id"))
            and _condition_digest_valid(cond_data)
        )
        projected_metrics = _project_metrics(cond_data.get("metrics")) if bound else None
        metric_value = projected_metrics.get(metric) if projected_metrics else None
        is_available = bound and metric_value is not None and cond_data.get("status") == "scored"
        points.append({
            "condition_id": cond_id,
            "budget": b,
            "labels_consumed": _safe_count(cond_data.get("labels_consumed")) if bound else None,
            "requested_method": method,
            "resolved_method": cond_data.get("resolved_method") if bound and cond_data.get("resolved_method") in APPROVED_CALIBRATORS else None,
            "status": cond_data.get("status") if bound and cond_data.get("status") in {"scored", "failed", "unavailable", "cancelled"} else "unavailable",
            "available": is_available,
            "metric_name": metric,
            "metric_value": metric_value if is_available else None,
            "unavailable_reason": None if is_available else "missing_or_mismatched_condition_context",
        })

    return ToolResult(
        tool_name="get_label_budget_curve",
        tool_call_id=tool_call_id,
        status="success",
        data={
            "experiment_id": exp_id,
            "predictor": pred,
            "scenario": scen,
            "method": method,
            "metric": metric,
            "points": points,
        },
    )


def calculate_decision_loss(
    params: CalculateDecisionLossParams, ctx: ToolContext, tool_call_id: str
) -> ToolResult:
    """Return exact persisted decision loss from cost grid for requested condition."""
    exp_id = params.experiment_id.strip()
    scen = params.scenario.strip().lower()
    pred = params.predictor.strip().lower()
    method = params.method.strip().lower()
    fp_cost = float(params.fp_cost)
    fn_cost = float(params.fn_cost)

    cost_pair = (fp_cost, fn_cost)
    if cost_pair not in SUPPORTED_COST_PAIRS:
        return ToolResult(
            tool_name="calculate_decision_loss",
            tool_call_id=tool_call_id,
            status="error",
            error=(
                f"{AgentErrorCode.UNSUPPORTED_COST_PAIR}: Cost pair (fp_cost={fp_cost}, fn_cost={fn_cost}) "
                f"is not in the persisted decision loss grid. Supported cost pairs are: "
                f"{sorted([list(cp) for cp in SUPPORTED_COST_PAIRS])}."
            ),
        )

    auth_err = _check_authorized(exp_id, ctx, "calculate_decision_loss", tool_call_id)
    if auth_err:
        return auth_err
    if scen not in APPROVED_SCENARIOS or pred not in APPROVED_PREDICTORS or method not in APPROVED_METHODS:
        return ToolResult(tool_name="calculate_decision_loss", tool_call_id=tool_call_id, status="error",
                          error=f"{AgentErrorCode.UNSUPPORTED_PARAMETER}: Unsupported scenario, predictor, or method.")

    repo = ExperimentRepository(ctx.engine)
    published = repo.get_published(exp_id)
    if not published:
        return ToolResult(
            tool_name="calculate_decision_loss",
            tool_call_id=tool_call_id,
            status="error",
            error=f"Experiment '{exp_id}' not found among PUBLISHED records.",
        )

    stored_exp, pub_rec = published
    payload = _get_payload(stored_exp)
    scen_key = f"{pred}__{scen}"
    dl_payload = (
        payload.get("payloads", {})
        .get("decision_loss", {})
        .get("scenarios", {})
        .get(scen_key, {})
        .get(method, {})
    )
    cost_losses = dl_payload.get("cost_grid_losses")

    if not cost_losses:
        # Check condition directly
        cond_key = f"{pred}__{scen}__b50__{method}"
        cond = payload.get("conditions", {}).get(cond_key)
        if cond and cond.get("metrics"):
            cost_losses = cond["metrics"].get("decision_loss")

    cond_key = f"{pred}__{scen}__b50__{method}"
    condition = payload.get("conditions", {}).get(cond_key)
    if not isinstance(condition, dict) or not all(
        key in condition for key in ("dataset_id", "predictor_id", "evaluation_rows_id", "test_mask_id", "source_map_id")
    ) or condition.get("scenario") != scen or condition.get("budget") != 50 or condition.get("predictor_name", condition.get("predictor")) != pred or (condition.get("requested_method") or condition.get("method")) != method or not _condition_digest_valid(condition):
        return ToolResult(tool_name="calculate_decision_loss", tool_call_id=tool_call_id, status="unavailable",
                          error=f"{AgentErrorCode.EXPERIMENT_UNAVAILABLE}: Decision-loss condition context is missing or mismatched.")
    condition_costs = (condition.get("metrics") or {}).get("decision_loss") if isinstance(condition.get("metrics"), dict) else None
    if not isinstance(condition_costs, list) or cost_losses != condition_costs:
        return ToolResult(tool_name="calculate_decision_loss", tool_call_id=tool_call_id, status="unavailable",
                          error=f"{AgentErrorCode.EXPERIMENT_UNAVAILABLE}: Cost rows are not bound to the referenced condition.")

    if not cost_losses:
        return ToolResult(
            tool_name="calculate_decision_loss",
            tool_call_id=tool_call_id,
            status="unavailable",
            error=f"No decision loss grid persisted for condition '{pred}__{scen}__b50__{method}' in experiment '{exp_id}'.",
        )

    matching_loss = None
    for entry in cost_losses:
        if abs(entry.get("fp_cost", 0.0) - fp_cost) < 1e-6 and abs(entry.get("fn_cost", 0.0) - fn_cost) < 1e-6:
            matching_loss = entry
            break

    if not matching_loss:
        return ToolResult(
            tool_name="calculate_decision_loss",
            tool_call_id=tool_call_id,
            status="error",
            error=f"{AgentErrorCode.UNSUPPORTED_COST_PAIR}: Cost pair ({fp_cost}, {fn_cost}) was not located in persisted grid.",
        )

    cond_id = _safe_condition_id(condition.get("condition_id"))
    if cond_id is None or dl_payload.get("condition_id", cond_id) != cond_id:
        return ToolResult(tool_name="calculate_decision_loss", tool_call_id=tool_call_id, status="unavailable",
                          error=f"{AgentErrorCode.EXPERIMENT_UNAVAILABLE}: Decision-loss reference is not bound to its condition.")

    result_data = {
        "experiment_id": exp_id,
        "condition_id": cond_id,
        "predictor": pred,
        "scenario": scen,
        "method": method,
        "budget": 50,
        "fp_cost": fp_cost,
        "fn_cost": fn_cost,
        "threshold": _safe_number(matching_loss.get("threshold")),
        "loss": _safe_number(matching_loss.get("loss")),
        "fp_count": _safe_count(matching_loss.get("fp_count")),
        "fn_count": _safe_count(matching_loss.get("fn_count")),
        "tp_count": _safe_count(matching_loss.get("tp_count")),
        "tn_count": _safe_count(matching_loss.get("tn_count")),
        "n_samples": _safe_count(matching_loss.get("n_samples")),
    }
    if result_data["loss"] is None:
        return ToolResult(
            tool_name="calculate_decision_loss",
            tool_call_id=tool_call_id,
            status="unavailable",
            error=f"{AgentErrorCode.EXPERIMENT_UNAVAILABLE}: Decision loss is null for the referenced condition.",
            data={**result_data, "unavailable_reason": "stored_decision_loss_is_null"},
        )

    return ToolResult(
        tool_name="calculate_decision_loss",
        tool_call_id=tool_call_id,
        status="success",
        data=result_data,
    )


def generate_result_summary(
    params: GenerateResultSummaryParams, ctx: ToolContext, tool_call_id: str
) -> ToolResult:
    """Generate grounded, deterministic Python summary of published experiment results."""
    exp_id = params.experiment_id.strip()
    focus = params.focus.strip().lower()

    auth_err = _check_authorized(exp_id, ctx, "generate_result_summary", tool_call_id)
    if auth_err:
        return auth_err

    from shiftguard.agent.policy import APPROVED_FOCUSES
    if focus not in APPROVED_FOCUSES:
        return ToolResult(
            tool_name="generate_result_summary",
            tool_call_id=tool_call_id,
            status="error",
            error=f"Focus '{params.focus}' is not approved. Permitted focuses: {sorted(list(APPROVED_FOCUSES))}",
        )

    repo = ExperimentRepository(ctx.engine)
    published = repo.get_published(exp_id)
    if not published:
        return ToolResult(
            tool_name="generate_result_summary",
            tool_call_id=tool_call_id,
            status="error",
            error=f"Experiment '{exp_id}' not found among PUBLISHED records.",
        )

    stored_exp, pub_rec = published
    payload = _get_payload(stored_exp)
    conditions = payload.get("conditions", {})

    total_conditions = len(conditions)
    scored_conditions = 0
    fallback_conditions = 0
    sparse_fallback_conditions = 0
    total_affected_fallback_rows = 0
    failed_conditions: list[dict[str, Any]] = []
    sparse_by_condition: dict[str, Any] = {}

    best_calibrator = None
    best_brier = float("inf")

    for k, v in conditions.items():
        if not isinstance(k, str) or not isinstance(v, dict) or not _is_safe_condition_key(k):
            continue
        status = v.get("status")
        if status == "scored":
            scored_conditions += 1
        if status in {"failed", "cancelled", "unavailable"} or v.get("metrics") is None:
            failed_conditions.append({
                "condition_key": k,
                "condition_id": _safe_condition_id(v.get("condition_id")),
                "status": status if status in {"failed", "cancelled", "unavailable"} else "unavailable",
                "requested_method": (v.get("requested_method") or v.get("method")) if (v.get("requested_method") or v.get("method")) in APPROVED_CALIBRATORS else None,
                "resolved_method": v.get("resolved_method") if v.get("resolved_method") in APPROVED_CALIBRATORS else None,
                "reason": _safe_reason(v.get("fallback_reason")) or "metrics_unavailable",
            })
        if v.get("resolved_method") != v.get("requested_method"):
            fallback_conditions += 1
        s_diag = _project_sparse_bin_diagnostics(v.get("sparse_bin_diagnostics"))
        if s_diag and isinstance(s_diag, dict):
            aff = s_diag.get("affected_fallback_rows", 0)
            if aff > 0:
                sparse_fallback_conditions += 1
                total_affected_fallback_rows += aff
            sparse_by_condition[k] = {
                "condition_id": _safe_condition_id(v.get("condition_id")),
                "requested_method": (v.get("requested_method") or v.get("method")) if (v.get("requested_method") or v.get("method")) in APPROVED_CALIBRATORS else None,
                "resolved_method": v.get("resolved_method") if v.get("resolved_method") in APPROVED_CALIBRATORS else None,
                "fallback_reason": _safe_reason(v.get("fallback_reason")),
                "sparse_bin_diagnostics": s_diag,
            }

        m = v.get("metrics")
        safe_metrics = _project_metrics(m)
        if safe_metrics and safe_metrics.get("brier_score") is not None:
            bs = float(safe_metrics["brier_score"])
            if bs < best_brier:
                best_brier = bs
                best_calibrator = {
                    "condition_key": k,
                    "condition_id": _safe_condition_id(v.get("condition_id")),
                    "predictor": (v.get("predictor") or v.get("predictor_name")) if (v.get("predictor") or v.get("predictor_name")) in APPROVED_PREDICTORS else None,
                    "scenario": v.get("scenario") if v.get("scenario") in APPROVED_SCENARIOS else None,
                    "method": (v.get("requested_method") or v.get("method")) if (v.get("requested_method") or v.get("method")) in APPROVED_CALIBRATORS else None,
                    "brier_score": bs,
                }

    comparisons = payload.get("comparisons", {}).get("pattern_comparison", {})

    summary_data = {
        "experiment_id": exp_id,
        "published_at": pub_rec.created_at,
        "focus": focus,
        "total_conditions": total_conditions,
        "scored_conditions": scored_conditions,
        "failed_conditions": failed_conditions,
        "sparse_diagnostics_by_condition": sparse_by_condition,
        "whole_condition_fallbacks": fallback_conditions,
        "sparse_bin_fallback_conditions": sparse_fallback_conditions,
        "total_affected_fallback_rows": total_affected_fallback_rows,
        "best_brier_condition": best_calibrator,
        "pattern_comparisons_present": bool(comparisons),
        "notes": (
            "Deterministic analytical summary computed from persisted verified records. "
            "Master seed 31001 illustrative single-seed execution."
        ),
    }

    return ToolResult(
        tool_name="generate_result_summary",
        tool_call_id=tool_call_id,
        status="success",
        data=summary_data,
    )
