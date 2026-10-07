"""Regressions for final rendering findings R04, R05, and R10."""

from __future__ import annotations

import json

from shiftguard.agent.rendering import ResultRenderer


EXPERIMENT_ID = "published-experiment-001"


def _condition(
    condition_id: str,
    *,
    metrics: dict | None,
    status: str = "scored",
    prediction_failed: bool = False,
    fit_status: str = "fitted",
    fallback_reason: str | None = None,
    sparse_bin_diagnostics: dict | None = None,
) -> dict:
    return {
        "condition_id": condition_id,
        "metrics": metrics,
        "status": status,
        "prediction_failed": prediction_failed,
        "fit_status": fit_status,
        "fallback_reason": fallback_reason,
        "method": "target_temperature",
        "resolved_method": "target_temperature",
        "sparse_bin_diagnostics": sparse_bin_diagnostics,
    }


def _trace(conditions: dict[str, dict]) -> list[dict]:
    # This is the persisted read-results projection consumed by the renderer.
    return [{
        "tool_name": "read_experiment_results",
        "result": {
            "status": "success",
            "data": {"experiment_id": EXPERIMENT_ID, "conditions": conditions},
        },
    }]


def test_healthy_summary_plan_retains_failed_adverse_and_null_conditions():
    conditions = {
        "healthy_condition": _condition(
            "condition-healthy",
            metrics={"brier_score": 0.2, "log_loss": 0.8, "ece": 0.1},
        ),
        "failed_condition": _condition(
            "condition-failed",
            metrics=None,
            status="failed",
            prediction_failed=True,
            fit_status="failed",
            fallback_reason="prediction_failed",
        ),
        "cancelled_condition": _condition(
            "condition-cancelled",
            metrics=None,
            status="cancelled",
            fit_status="cancelled",
            fallback_reason="execution_cancelled",
        ),
        "unavailable_condition": _condition(
            "condition-unavailable",
            metrics=None,
            status="unavailable",
            fit_status="unavailable",
            fallback_reason="source_record_unavailable",
        ),
        "null_metric_condition": _condition(
            "condition-null-metric",
            metrics={"brier_score": None},
            fallback_reason="metric_not_recorded",
        ),
    }
    plan = json.dumps({"template": "summary", "condition_refs": ["condition-healthy"]})

    rendered = ResultRenderer.ground_assistant_message(
        plan, _trace(conditions), [EXPERIMENT_ID], "Summarize every result",
    )

    expected = {
        "condition-failed": "prediction_failed",
        "condition-cancelled": "execution_cancelled",
        "condition-unavailable": "source_record_unavailable",
        "condition-null-metric": "metric_not_recorded",
    }
    adverse = [claim for claim in rendered["claims"] if claim["claim_type"] == "unavailable_observation"]
    observed = {claim.get("condition_id"): claim.get("reason") for claim in adverse}
    assert all(observed.get(condition_id) == reason for condition_id, reason in expected.items())
    assert all(
        next(claim for claim in adverse if claim.get("condition_id") == condition_id)["condition_key"]
        in rendered["summary"]
        for condition_id in expected
    )
    assert "prediction_failed" in rendered["summary"]
    assert "metric_not_recorded" in rendered["summary"]
    assert all(claim.get("condition_id") != "condition-healthy" for claim in adverse)


def test_fallback_plan_resolves_persisted_condition_id_and_retains_diagnostics():
    condition_id = "content-condition-9"
    conditions = {
        "logistic_regression__mcar_0_30__b50__raw": _condition(
            "content-condition-raw",
            metrics={"brier_score": 0.2},
            sparse_bin_diagnostics={"affected_fallback_rows": 0},
        ),
        "logistic_regression__mcar_0_30__b50__source_fraction_binned_temperature": _condition(
            condition_id,
            metrics={"brier_score": 0.1, "log_loss": 0.7, "ece": 0.05},
            fallback_reason="sparse_bin_support",
            sparse_bin_diagnostics={
                "affected_fallback_rows": 9,
                "sparse_prediction_failures": 0,
                "resolution_counts": {"source_remasked_temperature": 9},
                "bin_eval_counts": {"0": 10},
                "bin_fallback_counts": {"0": 9},
                "bin_support": {"0": 1},
                "bin_resolution_counts": {"0": {"source_remasked_temperature": 9}},
                "bin_resolved_maps": {"0": "source_remasked_temperature"},
            },
        ),
    }
    plan = json.dumps({"template": "fallbacks", "condition_refs": [condition_id]})

    rendered = ResultRenderer.ground_assistant_message(
        plan, _trace(conditions), [EXPERIMENT_ID], "Show fallback diagnostics",
    )

    assert rendered["fallback_analysis"] is not None
    fallback = rendered["fallback_analysis"][
        "logistic_regression__mcar_0_30__b50__source_fraction_binned_temperature"
    ]
    assert fallback["condition_id"] == condition_id
    assert fallback["sparse_bin_diagnostics"]["affected_fallback_rows"] == 9
    assert any(claim.get("condition_id") == condition_id for claim in rendered["claims"])
    assert "sparse_bin_support" in json.dumps(fallback)


def test_fallback_condition_id_is_not_confused_with_another_condition_key():
    colliding_id = "condition-key-that-is-not-a-content-id"
    conditions = {
        "ordinary_condition": _condition(
            colliding_id,
            metrics={"brier_score": 0.2},
        ),
        colliding_id: _condition(
            "actual-fallback-content-id",
            metrics={"brier_score": 0.1},
            fallback_reason="sparse_bin_support",
            sparse_bin_diagnostics={"affected_fallback_rows": 9},
        ),
    }

    collision_plan = json.dumps({"template": "fallbacks", "condition_refs": [colliding_id]})
    collision_result = ResultRenderer.ground_assistant_message(
        collision_plan, _trace(conditions), [EXPERIMENT_ID], "Show fallback diagnostics",
    )
    actual_id_plan = json.dumps({"template": "fallbacks", "condition_refs": ["actual-fallback-content-id"]})
    actual_id_result = ResultRenderer.ground_assistant_message(
        actual_id_plan, _trace(conditions), [EXPERIMENT_ID], "Show fallback diagnostics",
    )

    assert collision_result["claims"] == []
    assert actual_id_result["claims"]
    assert all(claim.get("condition_id") == "actual-fallback-content-id" for claim in actual_id_result["claims"])
