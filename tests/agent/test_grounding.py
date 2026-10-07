"""Tests for grounded result rendering, Python-owned numbers, and qualification assertions."""

from __future__ import annotations

import pytest

from shiftguard.agent.rendering import DISCLAIMER_TEXT, ResultRenderer
from shiftguard.agent.tools.results import _project_sparse_bin_diagnostics


def test_sparse_bin_diagnostics_projection():
    raw_telemetry = {
        "affected_fallback_rows": 9,
        "resolution_counts": {"fitted_bin_temperature": 8229, "source_remasked_temperature": 9},
        "bin_eval_counts": {0: 100, 8: 9},
        "bin_fallback_counts": {8: 9},
        "bin_support": {8: 8},
        "bin_resolution_counts": {8: {"source_remasked_temperature": 9}},
        "bin_resolved_maps": {8: "source_remasked_temperature"},
        "sparse_prediction_failures": 0,
        "failed_attempts": [{"sample_index": 1, "error": "internal_error"}],  # Must be excluded!
    }

    projected = _project_sparse_bin_diagnostics(raw_telemetry)
    assert projected is not None
    assert projected["affected_fallback_rows"] == 9
    assert projected["resolution_counts"] == {"fitted_bin_temperature": 8229, "source_remasked_temperature": 9}
    assert "failed_attempts" not in projected
    assert len(projected) == 8


def test_deterministic_rendering_includes_disclaimer_and_claims():
    trace = [
        {
            "ordinal": 1,
            "tool_name": "compare_calibrators",
            "result": {
                "status": "success",
                "data": {
                    "experiment_id": "exp_abc_12345",
                    "calibrator_comparisons": {
                        "raw": {"brier_score": 0.0850, "resolved_method": "raw", "comparison_qualified": True,
                                "condition_id": "condition-raw", "dataset_id": "dataset-id", "predictor_id": "predictor-id",
                                "evaluation_rows_id": "evaluation-id", "source_map_id": "source-map-id",
                                "scenario": "mcar_0_30", "budget": 50},
                        "target_temperature": {"brier_score": 0.0810, "resolved_method": "target_temperature",
                                               "comparison_qualified": True, "condition_id": "condition-target",
                                               "dataset_id": "dataset-id", "predictor_id": "predictor-id",
                                               "evaluation_rows_id": "evaluation-id", "source_map_id": "source-map-id",
                                               "scenario": "mcar_0_30", "budget": 50},
                    },
                },
            },
        }
    ]

    rendered = ResultRenderer.render_from_tool_results(
        prompt="Compare calibrators for MCAR 30%",
        tool_trace=trace,
        evidence_refs=["exp_abc_12345"],
    )

    assert "exp_abc_12345" in rendered["evidence_references"]
    assert rendered["disclaimer"] == DISCLAIMER_TEXT
    claims = rendered["claims"]
    assert len(claims) >= 1

    # Check that delta vs raw was computed deterministically by Python
    tt_claim = next(c for c in claims if c.get("method") == "target_temperature")
    assert pytest.approx(tt_claim["value"]) == 0.0810
    assert pytest.approx(tt_claim["delta"]) == -0.0040
    assert tt_claim["direction"] == "improved"


def test_decision_loss_rendering():
    trace = [
        {
            "ordinal": 1,
            "tool_name": "calculate_decision_loss",
            "result": {
                "status": "success",
                "data": {
                    "experiment_id": "exp_loss_test",
                    "fp_cost": 1.0,
                    "fn_cost": 4.0,
                    "threshold": 0.20,
                    "loss": 0.0450,
                    "fp_count": 10,
                    "fn_count": 5,
                },
            },
        }
    ]

    rendered = ResultRenderer.render_from_tool_results(
        prompt="Calculate decision loss for FP=1, FN=4",
        tool_trace=trace,
        evidence_refs=["exp_loss_test"],
    )

    assert rendered["decision_loss_points"] is not None
    assert len(rendered["decision_loss_points"]) == 1
    pt = rendered["decision_loss_points"][0]
    assert pt["fp_cost"] == 1.0
    assert pt["fn_cost"] == 4.0
    assert pt["threshold"] == 0.20
    assert pt["loss"] == 0.0450
