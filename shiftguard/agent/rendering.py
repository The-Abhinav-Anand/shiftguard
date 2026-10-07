"""Python-owned, evidence-authorized empirical rendering."""

from __future__ import annotations

import json
import math
import re
from typing import Any

from pydantic import ValidationError

from shiftguard.agent.policy import APPROVED_CALIBRATORS, APPROVED_PREDICTORS, APPROVED_SCENARIOS
from shiftguard.agent.schemas import ExplanationPlan
from shiftguard.agent.tools.projections import sanitize_public_error
from shiftguard.agent.tools.results import _project_sparse_bin_diagnostics

DISCLAIMER_TEXT = (
    "Evaluated on Bank Marketing with master seed 31001. "
    "Single-seed results are illustrative. Observed differences do not establish "
    "statistical significance or robust recovery without repeated-run uncertainty quantification."
)
_SAFE_TOOL_NAMES = frozenset({
    "calculate_decision_loss", "compare_calibrators", "compare_outages", "generate_result_summary",
    "get_experiment_metadata", "get_label_budget_curve", "inspect_dataset", "inspect_missingness",
    "list_available_scenarios", "read_experiment_results", "run_experiment", "run_stress_suite",
})
_ADVERSE_CONDITION_STATUSES = frozenset({"failed", "cancelled", "unavailable"})
_LABEL_BUDGETS = frozenset({0, 25, 50, 100, 200})
_CURVE_METRICS = frozenset({"brier_score", "log_loss"})
_CURVE_STATUSES = frozenset({"scored", "failed", "unavailable", "cancelled"})
_SAFE_REASON = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate JSON key")
        value[key] = item
    return value


def _reject_json_constant(_value: str) -> None:
    raise ValueError("Non-finite JSON number")


def parse_explanation_plan(
    content: str | None,
    authorized_condition_refs: set[str] | frozenset[str],
) -> ExplanationPlan | None:
    """Parse only the bounded presentation plan; reject prose and unknown fact references."""
    if not isinstance(content, str):
        return None
    try:
        if len(content.encode("utf-8")) > 4096:
            return None
        value = json.loads(content, object_pairs_hook=_unique_json_object, parse_constant=_reject_json_constant)
        plan = ExplanationPlan.model_validate(value)
    except (ValidationError, ValueError):
        return None
    except UnicodeEncodeError:
        return None
    if any(ref not in authorized_condition_refs for ref in plan.condition_refs):
        return None
    return plan


def explanation_plan_repair_message(authorized_condition_refs: set[str] | frozenset[str]) -> str:
    """Build the single bounded repair instruction from authorized condition IDs only."""
    refs = sorted(ref for ref in authorized_condition_refs if isinstance(ref, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", ref))[:16]
    return (
        "Return only a strict JSON explanation plan with keys template and condition_refs. "
        "Allowed templates: summary, comparisons, failures, fallbacks, costs. "
        f"Allowed condition_refs: {json.dumps(refs, separators=(',', ':'))}. "
        "Do not include prose, numbers, or claims."
    )


def _valid_comparison_context(raw: dict[str, Any], candidate: dict[str, Any]) -> bool:
    required = ("dataset_id", "predictor_id", "evaluation_rows_id", "source_map_id")
    if any(not isinstance(raw.get(key), str) or not isinstance(candidate.get(key), str) for key in required):
        return False
    if any(raw.get(key) != candidate.get(key) for key in required):
        return False
    return (
        raw.get("scenario") == candidate.get("scenario")
        and raw.get("budget") == candidate.get("budget")
        and raw.get("scenario") is not None
        and raw.get("budget") is not None
    )


class ResultRenderer:
    """Render only facts computed by Python from explicitly authorized tool results."""

    @staticmethod
    def render_from_tool_results(
        prompt: str,
        tool_trace: list[dict[str, Any]],
        evidence_refs: list[str],
    ) -> dict[str, Any]:
        del prompt  # User prose is never copied into an empirical result.
        allowed = {ref for ref in evidence_refs if isinstance(ref, str) and ref}
        claims: list[dict[str, Any]] = []
        fallback_by_condition: dict[str, dict[str, Any]] = {}
        cost_points: list[dict[str, Any]] = []
        tool_errors: list[dict[str, str]] = []
        refs_used: set[str] = set()

        for entry in tool_trace:
            name = entry.get("tool_name", "")
            result = entry.get("result") or {}
            status = result.get("status") or entry.get("status")
            data = result.get("data") or {}
            exp_id = data.get("experiment_id") if isinstance(data, dict) else None
            authorized = isinstance(exp_id, str) and exp_id in allowed
            raw_error = result.get("error") if isinstance(result, dict) else None
            if raw_error is None:
                raw_error = entry.get("error")
            if raw_error:
                safe_error = sanitize_public_error(raw_error)
                if isinstance(safe_error, dict):
                    code, message = safe_error["code"], safe_error["message"]
                else:
                    safe_text = safe_error or "EXPERIMENT_UNAVAILABLE: Published evidence is unavailable."
                    code, separator, message = safe_text.partition(": ")
                    if not separator:
                        code, message = "EXPERIMENT_UNAVAILABLE", "Published evidence is unavailable."
                safe_status = status if status in {"error", "failed", "cancelled", "unavailable", "success"} else "error"
                tool_errors.append({
                    "tool_name": name if name in _SAFE_TOOL_NAMES else "unknown_tool",
                    "status": safe_status, "code": code, "message": message,
                })
            if not authorized or status not in {"success", "unavailable"}:
                continue
            refs_used.add(exp_id)

            if name == "read_experiment_results":
                conditions = data.get("conditions")
                if isinstance(conditions, dict):
                    items = conditions.items()
                elif isinstance(data.get("condition_key"), str):
                    items = ((data["condition_key"], data),)
                else:
                    items = ()
                for condition_key, condition in items:
                    if not isinstance(condition, dict):
                        continue
                    metrics = condition.get("metrics") if isinstance(condition.get("metrics"), dict) else {}
                    condition_id = condition.get("condition_id")
                    condition_status = condition.get("status")
                    prediction_failed = condition.get("prediction_failed") is True
                    adverse = prediction_failed or condition_status in _ADVERSE_CONDITION_STATUSES
                    unavailable_status = (
                        condition_status if condition_status in _ADVERSE_CONDITION_STATUSES
                        else "failed" if prediction_failed
                        else "unavailable"
                    )
                    fallback_reason = condition.get("fallback_reason")
                    fit_status = condition.get("fit_status")
                    if isinstance(fallback_reason, str) and fallback_reason:
                        unavailable_reason = fallback_reason
                    elif adverse and isinstance(fit_status, str) and fit_status:
                        unavailable_reason = fit_status
                    elif prediction_failed:
                        unavailable_reason = "prediction_failed"
                    else:
                        unavailable_reason = "metrics_unavailable" if not metrics else "metric_unavailable"
                    unavailable_metrics: set[str] = set()
                    for metric in ("brier_score", "log_loss", "ece"):
                        value = metrics.get(metric)
                        if isinstance(value, (int, float)) and not isinstance(value, bool):
                            claims.append({
                                "claim_type": "metric_observation", "metric_name": metric,
                                "value": value, "condition_key": condition_key,
                                "condition_id": condition_id, "experiment_id": exp_id,
                                "description": f"{condition_key} {metric}: {value:.4f}",
                            })
                        elif metric in metrics and value is None:
                            claims.append({
                                "claim_type": "unavailable_observation", "metric_name": metric, "value": None,
                                "status": unavailable_status, "reason": unavailable_reason,
                                "condition_key": condition_key, "condition_id": condition_id, "experiment_id": exp_id,
                                "description": f"{condition_key} {metric} unavailable: {unavailable_reason}",
                            })
                            unavailable_metrics.add(metric)
                    if (adverse or not metrics) and "brier_score" not in unavailable_metrics:
                        claims.append({
                            "claim_type": "unavailable_observation", "metric_name": "brier_score", "value": None,
                            "status": unavailable_status, "reason": unavailable_reason,
                            "condition_key": condition_key, "condition_id": condition_id, "experiment_id": exp_id,
                            "description": f"{condition_key} unavailable: {unavailable_reason}",
                        })
                    sparse = condition.get("sparse_bin_diagnostics")
                    if isinstance(sparse, dict) or fallback_reason:
                        safe_sparse = _project_sparse_bin_diagnostics(sparse) if isinstance(sparse, dict) else {}
                        fallback_by_condition[str(condition_key)] = {
                            "condition_id": condition_id,
                            "requested_method": condition.get("method") or condition.get("requested_method"),
                            "resolved_method": condition.get("resolved_method"),
                            "fallback_reason": fallback_reason,
                            "sparse_bin_diagnostics": safe_sparse or {},
                        }

            elif name == "get_label_budget_curve":
                points = data.get("points")
                if isinstance(points, list):
                    scenario = data.get("scenario") if data.get("scenario") in APPROVED_SCENARIOS else None
                    predictor = data.get("predictor") if data.get("predictor") in APPROVED_PREDICTORS else None
                    for point in points:
                        if not isinstance(point, dict):
                            continue
                        condition_id = point.get("condition_id")
                        budget = point.get("budget")
                        requested_method = point.get("requested_method")
                        metric_name = point.get("metric_name")
                        if (
                            not isinstance(condition_id, str)
                            or not re.fullmatch(r"[a-f0-9]{24}", condition_id)
                            or type(budget) is not int
                            or budget not in _LABEL_BUDGETS
                            or requested_method not in APPROVED_CALIBRATORS
                            or metric_name not in _CURVE_METRICS
                        ):
                            continue
                        resolved_method = point.get("resolved_method")
                        if resolved_method not in APPROVED_CALIBRATORS:
                            resolved_method = None
                        labels_consumed = point.get("labels_consumed")
                        if type(labels_consumed) is not int or labels_consumed < 0:
                            labels_consumed = None
                        point_status = point.get("status")
                        if point_status not in _CURVE_STATUSES:
                            point_status = "unavailable"
                        value = point.get("metric_value")
                        available = (
                            point.get("available") is True
                            and isinstance(value, (int, float))
                            and not isinstance(value, bool)
                            and math.isfinite(float(value))
                        )
                        observation = {
                            "condition_id": condition_id,
                            "experiment_id": exp_id,
                            "budget": budget,
                            "labels_consumed": labels_consumed,
                            "requested_method": requested_method,
                            "resolved_method": resolved_method,
                            "metric_name": metric_name,
                            "status": point_status,
                        }
                        scenario_label = scenario or "approved scenario"
                        predictor_label = f"{predictor} " if predictor else ""
                        resolved_label = (
                            f" (resolved to {resolved_method})"
                            if resolved_method is not None and resolved_method != requested_method
                            else ""
                        )
                        labels_label = (
                            f"; labels consumed: {labels_consumed}"
                            if labels_consumed is not None else ""
                        )
                        if available:
                            observation.update({
                                "claim_type": "budget_curve_observation",
                                "value": value,
                                "available": True,
                                "description": (
                                    f"{predictor_label}{scenario_label} budget {budget} "
                                    f"{requested_method}{resolved_label} {metric_name}: {value:.4f}"
                                    f"{labels_label}"
                                ),
                            })
                        else:
                            raw_reason = point.get("unavailable_reason")
                            reason = raw_reason if isinstance(raw_reason, str) and _SAFE_REASON.fullmatch(raw_reason) else "metric_unavailable"
                            observation.update({
                                "claim_type": "unavailable_budget_curve_observation",
                                "value": None,
                                "available": False,
                                "reason": reason,
                                "description": (
                                    f"{predictor_label}{scenario_label} budget {budget} "
                                    f"{requested_method}{resolved_label} {metric_name} unavailable: {reason}"
                                    f"{labels_label}"
                                ),
                            })
                        claims.append(observation)

            elif name == "compare_calibrators":
                comparisons = data.get("calibrator_comparisons", {})
                raw = comparisons.get("raw") if isinstance(comparisons, dict) else None
                raw_brier = raw.get("brier_score") if isinstance(raw, dict) else None
                for method, item in comparisons.items() if isinstance(comparisons, dict) else ():
                    if not isinstance(item, dict):
                        continue
                    value = item.get("brier_score")
                    context_ok = isinstance(raw, dict) and _valid_comparison_context(raw, item)
                    qualified = item.get("comparison_qualified") is True and context_ok
                    delta = float(value) - float(raw_brier) if isinstance(value, (int, float)) and isinstance(raw_brier, (int, float)) else None
                    direction = "unqualified"
                    if qualified and delta is not None:
                        direction = "improved" if delta < -1e-5 else ("degraded" if delta > 1e-5 else "unchanged")
                    if value is None:
                        claims.append({
                            "claim_type": "unavailable_comparison", "method": method,
                            "condition_id": item.get("condition_id"), "status": item.get("status", "unavailable"),
                            "reason": item.get("qualification_reason") or "metric_unavailable", "experiment_id": exp_id,
                            "description": f"{method} comparison unavailable: {item.get('qualification_reason') or 'metric_unavailable'}",
                        })
                    else:
                        claims.append({
                            "claim_type": "calibrator_comparison", "method": method,
                            "condition_id": item.get("condition_id"), "description": f"{method} Brier score: {value:.4f}",
                            "metric_name": "brier_score", "value": value, "baseline_value": raw_brier,
                            "delta": delta, "direction": direction, "comparison_qualified": qualified,
                            "qualification_reason": item.get("qualification_reason") if not qualified else None,
                            "resolved_method": item.get("resolved_method"), "experiment_id": exp_id,
                        })

            elif name == "compare_outages":
                comp = data.get("comparison", {})
                methods = comp.get("methods", {}) if isinstance(comp, dict) else {}
                for method, item in methods.items() if isinstance(methods, dict) else ():
                    if not isinstance(item, dict):
                        continue
                    delta = item.get("delta_brier")
                    qualified = item.get("comparison_qualified") is True and item.get("available") is True
                    if delta is None:
                        claims.append({"claim_type": "unavailable_comparison", "method": method,
                                       "condition_id": item.get("block_condition_id"), "status": "unavailable",
                                       "reason": item.get("qualification_reason") or "metrics_unavailable",
                                       "experiment_id": exp_id,
                                       "description": f"{method} outage comparison unavailable: {item.get('qualification_reason') or 'metrics_unavailable'}"})
                    else:
                        claims.append({
                            "claim_type": "outage_pattern_comparison", "method": method,
                            "description": f"{method} block versus matched cellwise MCAR delta Brier: {delta:+.4f}",
                            "delta": delta, "block_brier": item.get("block_brier"),
                            "cellwise_brier": item.get("cellwise_brier"),
                            "comparison_qualified": qualified,
                            "qualification_reason": item.get("qualification_reason"),
                            "condition_id": item.get("block_condition_id"), "experiment_id": exp_id,
                        })

            elif name == "calculate_decision_loss":
                loss = data.get("loss")
                item = {
                    "condition_id": data.get("condition_id"), "fp_cost": data.get("fp_cost"),
                    "fn_cost": data.get("fn_cost"), "threshold": data.get("threshold"),
                    "loss": loss, "fp_count": data.get("fp_count"), "fn_count": data.get("fn_count"),
                    "status": status if loss is None or status != "success" else "success",
                    "unavailable_reason": data.get("unavailable_reason"), "experiment_id": exp_id,
                }
                cost_points.append(item)
                if loss is None or status != "success":
                    claims.append({
                        "claim_type": "unavailable_decision_loss", "condition_id": data.get("condition_id"),
                        "metric_name": "decision_loss", "value": None, "status": status,
                        "reason": data.get("unavailable_reason") or "decision_loss_unavailable", "experiment_id": exp_id,
                        "description": f"Decision loss unavailable for condition {data.get('condition_id')}: {data.get('unavailable_reason') or 'stored value is null'}",
                    })
                else:
                    claims.append({
                        "claim_type": "decision_loss_evaluation", "condition_id": data.get("condition_id"),
                        "description": f"Cost pair FP={data.get('fp_cost')}/FN={data.get('fn_cost')}: threshold={data.get('threshold')}, loss={loss}",
                        "metric_name": "decision_loss", "value": loss, "experiment_id": exp_id,
                    })

            elif name == "generate_result_summary":
                best = data.get("best_brier_condition")
                if isinstance(best, dict) and isinstance(best.get("brier_score"), (int, float)):
                    claims.append({"claim_type": "best_calibrator_summary", "description": f"Best Brier score: {best['brier_score']:.4f}",
                                   "metric_name": "brier_score", "value": best["brier_score"],
                                   "condition_key": best.get("condition_key"), "condition_id": best.get("condition_id"),
                                   "experiment_id": exp_id})
                for failed in data.get("failed_conditions", []) if isinstance(data.get("failed_conditions"), list) else []:
                    if isinstance(failed, dict):
                        claims.append({"claim_type": "unavailable_observation", "condition_key": failed.get("condition_key"),
                                       "condition_id": failed.get("condition_id"), "status": failed.get("status"),
                                       "reason": failed.get("reason"), "experiment_id": exp_id,
                                       "description": f"{failed.get('condition_key')} {failed.get('status')}: {failed.get('reason')}"})
                sparse = data.get("sparse_diagnostics_by_condition")
                if isinstance(sparse, dict):
                    fallback_by_condition.update(sparse)

        summary_lines = []
        if claims:
            summary_lines.append(f"Grounded analysis from {len(refs_used)} authorized experiment reference(s):")
            summary_lines.extend(f"• {claim['description']}" for claim in claims)
        else:
            summary_lines.append("No authorized published evidence is available for empirical claims.")
        for error in tool_errors:
            summary_lines.append(f"{error['status']}: {error['code']}: {error['message']}")
        if fallback_by_condition:
            summary_lines.append(f"Fallback diagnostics are retained for {len(fallback_by_condition)} condition(s).")

        return {
            "title": "Calibration analysis",
            "summary": "\n".join(summary_lines),
            "claims": claims,
            "fallback_analysis": fallback_by_condition or None,
            "decision_loss_points": cost_points or None,
            "tool_errors": tool_errors,
            "evidence_references": sorted(refs_used),
            "disclaimer": DISCLAIMER_TEXT,
        }

    @staticmethod
    def ground_assistant_message(
        assistant_text: str | None,
        tool_trace: list[dict[str, Any]],
        evidence_refs: list[str],
        prompt: str,
    ) -> dict[str, Any]:
        """Treat provider content as a strict plan; render all empirical text in Python."""
        rendered = ResultRenderer.render_from_tool_results(prompt, tool_trace, evidence_refs)
        condition_refs = {
            claim["condition_id"] for claim in rendered["claims"]
            if isinstance(claim.get("condition_id"), str) and claim["condition_id"]
        }
        plan = parse_explanation_plan(assistant_text, condition_refs)
        if plan is None:
            rendered["provider_narrative"] = rendered["summary"]
            return rendered

        selected = list(rendered["claims"])
        if plan.condition_refs:
            selected = [claim for claim in selected if claim.get("condition_id") in plan.condition_refs]
        if plan.template == "comparisons":
            selected = [claim for claim in selected if "comparison" in claim.get("claim_type", "")]
        elif plan.template == "failures":
            selected = [claim for claim in selected if claim.get("status") in {"failed", "cancelled", "unavailable"} or "unavailable" in claim.get("claim_type", "")]
        elif plan.template == "fallbacks":
            fallback_analysis = rendered.get("fallback_analysis")
            fallback_condition_refs = {
                item.get("condition_id")
                for item in fallback_analysis.values()
                if isinstance(item, dict) and isinstance(item.get("condition_id"), str) and item["condition_id"]
            } if isinstance(fallback_analysis, dict) else set()
            selected = [claim for claim in selected if claim.get("condition_id") in fallback_condition_refs]
        elif plan.template == "costs":
            selected = [claim for claim in selected if "decision_loss" in claim.get("claim_type", "")]
        mandatory = [
            claim for claim in rendered["claims"]
            if claim.get("status") in _ADVERSE_CONDITION_STATUSES
            or str(claim.get("claim_type", "")).startswith("unavailable_")
            or ("value" in claim and claim.get("value") is None)
        ]
        mandatory_ids = {id(claim) for claim in mandatory}
        selected = [claim for claim in selected if id(claim) not in mandatory_ids]
        selected.extend(mandatory)
        text_lines = [f"Grounded {plan.template} from {len(rendered['evidence_references'])} authorized experiment reference(s):"]
        text_lines.extend(claim["description"] for claim in selected)
        if not selected:
            text_lines.append("No matching authorized facts are available.")
        rendered["claims"] = selected
        rendered["summary"] = "\n".join(text_lines)
        rendered["provider_explanation_plan"] = plan.model_dump(mode="json")
        rendered["provider_narrative"] = rendered["summary"]
        return rendered
