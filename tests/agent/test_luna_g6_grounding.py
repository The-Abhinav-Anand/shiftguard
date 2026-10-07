"""Permanent C2 regressions for authorized facts and Python-owned narratives."""

from __future__ import annotations

import json

from shiftguard.agent.rendering import ResultRenderer, explanation_plan_repair_message, parse_explanation_plan
from shiftguard.agent.tools.results import _project_sparse_bin_diagnostics


EXPERIMENT = "exp_abc123"
CONTEXT = {
    "dataset_id": "dataset-id",
    "predictor_id": "predictor-id",
    "evaluation_rows_id": "evaluation-id",
    "source_map_id": "source-map-id",
    "scenario": "mcar_0_30",
    "budget": 50,
}


def _comparison_trace() -> list[dict]:
    raw = {"condition_id": "condition-raw", "brier_score": 0.2, "resolved_method": "raw",
           "comparison_qualified": True, **CONTEXT}
    target = {"condition_id": "condition-target", "brier_score": 0.1,
              "resolved_method": "target_temperature", "comparison_qualified": True, **CONTEXT}
    return [{"tool_name": "compare_calibrators", "result": {"status": "success", "data": {
        "experiment_id": EXPERIMENT,
        "calibrator_comparisons": {"raw": raw, "target_temperature": target},
    }}}]


def test_luna_g6_empty_evidence_set_grants_no_empirical_claims():
    trace = _comparison_trace()
    rendered = ResultRenderer.render_from_tool_results("compare", trace, [])
    assert rendered["claims"] == []
    assert rendered["evidence_references"] == []
    assert "No authorized published evidence" in rendered["summary"]


def test_luna_g6_valid_evidence_does_not_authorize_unchecked_provider_prose():
    false_text = "Brier score is 0.0000; calibration improved. The method recovered and is superior; statistically significant improvement. All 82 rows recovered."
    rendered = ResultRenderer.ground_assistant_message(false_text, _comparison_trace(), [EXPERIMENT], "private prompt")
    target = next(claim for claim in rendered["claims"] if claim.get("method") == "target_temperature")
    assert target["value"] == 0.1
    assert target["delta"] == -0.1
    assert target["direction"] == "improved"
    assert "0.0000" not in rendered["summary"]
    assert "statistically significant" not in rendered["provider_narrative"].lower()
    assert "82 rows" not in rendered["provider_narrative"]
    assert "private prompt" not in rendered["title"]


def test_luna_g6_explanation_plan_is_strict_allowlisted_and_reference_bound():
    condition_id = "condition-target"
    valid = json.dumps({"template": "comparisons", "condition_refs": [condition_id]})
    plan = parse_explanation_plan(valid, {condition_id})
    assert plan is not None and plan.template == "comparisons"
    assert parse_explanation_plan("The method improved by 0.1", {condition_id}) is None
    assert parse_explanation_plan(json.dumps({"template": "summary", "condition_refs": ["foreign"]}), {condition_id}) is None
    assert parse_explanation_plan(json.dumps({"template": "summary", "condition_refs": [], "narrative": "claim"}), set()) is None
    assert parse_explanation_plan('{"template":"summary","template":"costs","condition_refs":[]}', set()) is None
    assert parse_explanation_plan('{"template":"summary","condition_refs":[],"value":NaN}', set()) is None
    repair = explanation_plan_repair_message({condition_id, "C:\\private\\labels.csv"})
    assert condition_id in repair
    assert "private" not in repair


def test_luna_g6_failed_ninth_condition_and_all_sparse_diagnostics_are_retained():
    sparse = {
        "affected_fallback_rows": 9,
        "resolution_counts": {"fitted_bin_temperature": 8, "source_remasked_temperature": 1, "api_key": 100},
        "bin_eval_counts": {0: 100, 8: 9, 12: 5},
        "bin_fallback_counts": {8: 9},
        "bin_support": {8: 8},
        "bin_resolution_counts": {8: {"source_remasked_temperature": 9, "api_key": 3}},
        "bin_resolved_maps": {8: "source_remasked_temperature", 9: "C:\\private\\path"},
        "sparse_prediction_failures": 0,
        "failed_attempts": [{"raw_labels": [0, 1]}],
    }
    projected = _project_sparse_bin_diagnostics(sparse)
    assert projected is not None
    assert set(projected) == {
        "affected_fallback_rows", "resolution_counts", "bin_eval_counts", "bin_fallback_counts",
        "bin_support", "bin_resolution_counts", "bin_resolved_maps", "sparse_prediction_failures",
    }
    assert "api_key" not in json.dumps(projected)
    assert "private" not in json.dumps(projected)

    conditions = {}
    for index in range(9):
        key = f"condition_{index}"
        conditions[key] = {
            "condition_id": f"condition-id-{index}",
            "metrics": {"brier_score": 0.1 + index / 100} if index < 8 else None,
            "status": "scored" if index < 8 else "failed",
            "prediction_failed": index == 8,
            "fit_status": "fitted" if index < 8 else "failed",
            "fallback_reason": "prediction_failed" if index == 8 else None,
            "method": "source_fraction_binned_temperature",
            "resolved_method": "source_remasked_temperature",
            "sparse_bin_diagnostics": sparse,
        }
    trace = [{"tool_name": "read_experiment_results", "result": {"status": "success", "data": {
        "experiment_id": EXPERIMENT, "conditions": conditions,
    }}}]
    rendered = ResultRenderer.render_from_tool_results("read", trace, [EXPERIMENT])
    ninth = next(c for c in rendered["claims"] if c.get("condition_key") == "condition_8")
    assert ninth["status"] == "failed"
    assert len(rendered["fallback_analysis"]) == 9
    assert set(rendered["fallback_analysis"]["condition_8"]["sparse_bin_diagnostics"]) == {
        "affected_fallback_rows", "resolution_counts", "bin_eval_counts", "bin_fallback_counts",
        "bin_support", "bin_resolution_counts", "bin_resolved_maps", "sparse_prediction_failures",
    }


def test_luna_g6_typed_cost_error_and_null_loss_keep_condition_reference():
    trace = [
        {"tool_name": "calculate_decision_loss", "result": {
            "status": "error", "error": "UNSUPPORTED_COST_PAIR: arbitrary private details",
        }},
        {"tool_name": "calculate_decision_loss", "result": {
            "status": "unavailable", "error": "EXPERIMENT_UNAVAILABLE: loss is null",
            "data": {"experiment_id": EXPERIMENT, "condition_id": "condition-null", "loss": None,
                     "fp_cost": 1.0, "fn_cost": 4.0, "unavailable_reason": "stored_decision_loss_is_null"},
        }},
    ]
    rendered = ResultRenderer.render_from_tool_results("cost", trace, [EXPERIMENT])
    assert rendered["tool_errors"][0]["code"] == "UNSUPPORTED_COST_PAIR"
    unavailable = next(c for c in rendered["claims"] if c["claim_type"] == "unavailable_decision_loss")
    assert unavailable["condition_id"] == "condition-null"
    assert unavailable["status"] == "unavailable"


def test_luna_g6_incompatible_or_missing_identity_never_gets_improvement_direction():
    trace = _comparison_trace()
    methods = trace[0]["result"]["data"]["calibrator_comparisons"]
    methods["target_temperature"]["predictor_id"] = "different-predictor"
    rendered = ResultRenderer.render_from_tool_results("compare", trace, [EXPERIMENT])
    target = next(claim for claim in rendered["claims"] if claim.get("method") == "target_temperature")
    assert target["direction"] == "unqualified"
    assert target["comparison_qualified"] is False

    for key in ("dataset_id", "predictor_id", "evaluation_rows_id", "source_map_id"):
        methods["target_temperature"].pop(key)
    rendered_missing = ResultRenderer.render_from_tool_results("compare", trace, [EXPERIMENT])
    target_missing = next(claim for claim in rendered_missing["claims"] if claim.get("method") == "target_temperature")
    assert target_missing["direction"] == "unqualified"
