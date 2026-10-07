"""End-to-end regressions for the G6 grounding correction batch."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine

from shiftguard.agent.registry import ToolRegistry
from shiftguard.agent.rendering import ResultRenderer
from shiftguard.agent.schemas import ToolResult
from shiftguard.agent.tools import ToolContext
from shiftguard.experiments.ids import stable_hash
from shiftguard.settings import Settings
from shiftguard.storage.repositories import ExperimentRepository


EXPERIMENT_ID = "a" * 24
METHOD = "source_fraction_binned_temperature"
SCENARIO = "mcar_0_30"


@pytest.fixture
def boundary(monkeypatch, tmp_path):
    engine = create_engine("sqlite://")
    context = ToolContext(
        engine=engine,
        settings=Settings(SHIFTGUARD_DB_URL=f"sqlite:///{tmp_path / 'grounding.db'}"),
        session_id="grounding-test-session",
        authorized_experiment_ids=frozenset({EXPERIMENT_ID}),
    )

    def dispatch(payload, tool_name, arguments):
        stored = SimpleNamespace(deterministic_payload=payload, experiment_id=EXPERIMENT_ID)
        publication = SimpleNamespace(created_at="2026-10-03T00:00:00Z")
        monkeypatch.setattr(
            ExperimentRepository,
            "get_published",
            lambda _repo, requested_id: (stored, publication) if requested_id == EXPERIMENT_ID else None,
        )
        return ToolRegistry().dispatch(tool_name, arguments, context, f"call-{tool_name}")

    yield context, dispatch
    engine.dispose()


def _condition(condition_id: str, metrics: dict | None, diagnostics: dict | None = None) -> dict:
    return {
        "condition_id": condition_id,
        "predictor": "logistic_regression",
        "predictor_name": "logistic_regression",
        "predictor_id": "b" * 64,
        "dataset_id": "c" * 64,
        "evaluation_rows_id": "d" * 64,
        "source_map_id": "e" * 64,
        "test_mask_id": "f" * 64,
        "scenario": SCENARIO,
        "budget": 50,
        "method": METHOD,
        "requested_method": METHOD,
        "resolved_method": METHOD,
        "status": "scored",
        "fit_status": "fitted",
        "fallback_chain": [],
        "labels_consumed": 0,
        "prediction_failed": False,
        "metrics": metrics,
        "sparse_bin_diagnostics": diagnostics,
        "fitted_parameters": {"private_parameter": "grounding-secret-marker"},
    }


def _trace(result: ToolResult) -> list[dict]:
    return [{"tool_name": result.tool_name, "result": result.model_dump(mode="json")}]


def test_registry_rejects_non_integer_and_unsupported_label_budgets_before_handlers(boundary, monkeypatch):
    context, _dispatch = boundary
    registry = ToolRegistry()
    for name in ("compare_calibrators", "compare_outages"):
        seen: list[int] = []

        def handler(params, _context, call_id):
            seen.append(params.budget)
            return ToolResult(tool_name=name, tool_call_id=call_id, status="success")

        monkeypatch.setattr(registry._tools[name], "handler", handler)
        base = {"experiment_id": EXPERIMENT_ID}
        if name == "compare_calibrators":
            base["scenario"] = SCENARIO

        for value in (False, True, 0.0, 50.0, "50", None, 201):
            result = registry.dispatch(name, json.dumps({**base, "budget": value}), context, f"invalid-{name}")
            assert result.status == "error"
            assert seen == []

        for value in (0, 25, 50, 100, 200):
            result = registry.dispatch(name, json.dumps({**base, "budget": value}), context, f"valid-{name}")
            assert result.status == "success"
        assert registry.dispatch(name, base, context, f"default-{name}").status == "success"
        assert seen == [0, 25, 50, 100, 200, 50]


def test_read_results_preserves_only_allowed_bin_states_and_explicit_null_metrics(boundary):
    _context, dispatch = boundary
    diagnostics = {
        "bin_eval_counts": {"0": 2, "1": 0, "2": 2, "9": "bad", "secret-bin": 99},
        "bin_resolution_counts": {
            "0": {"raw": 1, "source_temperature": 1, "mixed": 7, "secret_method": 8},
            "bad-bin": {"raw": 4},
        },
        "bin_resolved_maps": {
            "0": "mixed", "1": "empty", "2": "source_temperature",
            "9": "secret_method", "secret-bin": "mixed",
        },
        "api_key": "private-grounding-marker",
        "failed_attempts": [{"details": "private-grounding-marker"}],
    }
    conditions = {
        f"logistic_regression__{SCENARIO}__b50__{METHOD}": _condition(
            "1" * 24, {"brier_score": 0.2, "log_loss": None, "ece": 0.1}, diagnostics,
        ),
        f"logistic_regression__{SCENARIO}__b50__raw": _condition(
            "2" * 24, {"brier_score": 0.15}, {},
        ),
        "private_condition_key": {"metrics": {"brier_score": 99}, "api_key": "private-grounding-marker"},
    }
    result = dispatch({"conditions": conditions}, "read_experiment_results", {"experiment_id": EXPERIMENT_ID})
    assert result.status == "success"
    projected = result.data["conditions"]
    condition = projected[f"logistic_regression__{SCENARIO}__b50__{METHOD}"]
    assert condition["sparse_bin_diagnostics"]["bin_resolved_maps"] == {
        "0": "mixed", "1": "empty", "2": "source_temperature",
    }
    assert condition["sparse_bin_diagnostics"]["bin_resolution_counts"] == {
        "0": {"raw": 1, "source_temperature": 1},
    }
    assert condition["metrics"] == {"brier_score": 0.2, "log_loss": None, "ece": 0.1}
    raw_condition = projected[f"logistic_regression__{SCENARIO}__b50__raw"]
    assert raw_condition["metrics"] == {"brier_score": 0.15}

    trace = _trace(result)
    rendered = ResultRenderer.ground_assistant_message(
        json.dumps({"template": "summary", "condition_refs": ["1" * 24]}),
        trace,
        [EXPERIMENT_ID],
        "Summarize the selected result",
    )
    claim_types = [claim["claim_type"] for claim in rendered["claims"]]
    assert "metric_observation" in claim_types
    null_claim = next(
        claim for claim in rendered["claims"]
        if claim.get("metric_name") == "log_loss" and claim.get("condition_id") == "1" * 24
    )
    assert null_claim["claim_type"] == "unavailable_observation"
    unplanned = ResultRenderer.render_from_tool_results("", trace, [EXPERIMENT_ID])
    assert {claim.get("metric_name") for claim in unplanned["claims"] if claim.get("condition_id") == "2" * 24} == {"brier_score"}
    sparse = rendered["fallback_analysis"][f"logistic_regression__{SCENARIO}__b50__{METHOD}"]["sparse_bin_diagnostics"]
    assert sparse["bin_resolved_maps"] == {"0": "mixed", "1": "empty", "2": "source_temperature"}
    assert "private-grounding-marker" not in json.dumps(result.model_dump(mode="json"))
    assert "private-grounding-marker" not in json.dumps(rendered)
    assert "private_condition_key" not in json.dumps(result.model_dump(mode="json"))


def test_inspect_missingness_keeps_sanitized_gate2_and_gate3_rate_layouts(boundary):
    _context, dispatch = boundary
    pool_rates = {
        "row_count": 100,
        "requested_rate": 0.3,
        "newly_missing_cells": 30,
        "total_missing_rate_over_all_feature_cells": 0.3,
        "private_rate": 999,
        "row_count_secret": 101,
    }
    outage_rates = {
        "row_count": 80,
        "requested_row_probability": 0.5,
        "realized_selected_row_fraction": 0.4,
        "observed_history_group_new_missing_rate": 0.4,
        "api_key": "private-mask-marker",
    }
    masks = {
        "mcar_0_30_rates": pool_rates,
        "history_block_pool_rates": outage_rates,
        "history_block_pool_mask_id": "a" * 64,
        "full_pool": {
            "mask_id": "b" * 64,
            "rates": {**pool_rates, "private_rate": 1000},
            "record_ids": ["private-mask-marker"],
            "api_key": "private-mask-marker",
        },
        "acquired_subset": {
            "parent_mask_id": "b" * 64,
            "rates": {"row_count": 20, "selected_rows": 8, "secret": 44},
        },
        "test": {
            "mask_id": "c" * 64,
            "rates": {"row_count": 40, "total_missing_cells": 12},
        },
        "api_key": "private-mask-marker",
    }
    result = dispatch({"masks": masks}, "inspect_missingness", {"experiment_id": EXPERIMENT_ID})
    assert result.status == "success"
    projected = result.data["realized_mask_summaries"]
    assert projected["mcar_0_30_rates"] == {
        "row_count": 100,
        "requested_rate": 0.3,
        "newly_missing_cells": 30,
        "total_missing_rate_over_all_feature_cells": 0.3,
    }
    assert projected["history_block_pool_rates"] == {
        "row_count": 80,
        "requested_row_probability": 0.5,
        "realized_selected_row_fraction": 0.4,
        "observed_history_group_new_missing_rate": 0.4,
    }
    assert projected["full_pool"]["rates"]["newly_missing_cells"] == 30
    assert projected["acquired_subset"]["rates"] == {"row_count": 20, "selected_rows": 8}
    assert projected["test"]["rates"] == {"row_count": 40, "total_missing_cells": 12}
    serialized = json.dumps(result.model_dump(mode="json"))
    assert "private-mask-marker" not in serialized
    assert "private_rate" not in serialized
    assert "row_count_secret" not in serialized


def _budget_curve_payload() -> tuple[dict, dict[int, str], dict[int, int]]:
    conditions: dict[str, dict] = {}
    points = []
    condition_ids: dict[int, str] = {}
    labels_by_budget = {0: 0, 25: 7, 50: 12, 100: 19, 200: 23}
    for budget in (0, 25, 50, 100, 200):
        condition = {
            "predictor_name": "logistic_regression",
            "dataset_id": "c" * 64,
            "predictor_id": "d" * 64,
            "evaluation_rows_id": "e" * 64,
            "test_mask_id": "f" * 64,
            "source_map_id": "1" * 64,
            "scenario": SCENARIO,
            "budget": budget,
            "requested_method": METHOD,
            "resolved_method": METHOD,
            "labels_consumed": labels_by_budget[budget],
            "status": "unavailable" if budget == 50 else "scored",
            "metrics": {"brier_score": None if budget == 50 else 0.2 - budget / 10000},
            "api_key": "private-curve-marker",
        }
        condition["condition_id"] = stable_hash(condition)[:24]
        condition_ids[budget] = condition["condition_id"]
        conditions[f"logistic_regression__{SCENARIO}__b{budget}__{METHOD}"] = condition
        points.append({"budget": budget, "condition_id": condition["condition_id"]})
    payload = {
        "conditions": conditions,
        "payloads": {
            "budget_curve": {
                "scenarios": {f"logistic_regression__{SCENARIO}": {METHOD: points}},
            },
        },
        "private_nested": {"token": "private-curve-marker"},
    }
    return payload, condition_ids, labels_by_budget


def test_budget_curve_registry_handler_projection_renderer_and_plan_keep_all_observations(boundary):
    _context, dispatch = boundary
    payload, condition_ids, labels_by_budget = _budget_curve_payload()
    result = dispatch(
        payload,
        "get_label_budget_curve",
        {"experiment_id": EXPERIMENT_ID, "scenario": SCENARIO},
    )
    assert result.status == "success"
    assert len(result.data["points"]) == 5
    assert sum(point["available"] is True for point in result.data["points"]) == 4
    trace = _trace(result)

    rendered = ResultRenderer.render_from_tool_results("Show the saved curve", trace, [EXPERIMENT_ID])
    assert len(rendered["claims"]) == 5
    assert "No authorized published evidence" not in rendered["summary"]
    by_budget = {claim["budget"]: claim for claim in rendered["claims"]}
    assert set(by_budget) == {0, 25, 50, 100, 200}
    for budget in (0, 25, 100, 200):
        claim = by_budget[budget]
        assert claim["claim_type"] == "budget_curve_observation"
        assert claim["condition_id"] == condition_ids[budget]
        assert claim["experiment_id"] == EXPERIMENT_ID
        assert claim["labels_consumed"] == labels_by_budget[budget]
        assert claim["requested_method"] == METHOD
        assert claim["resolved_method"] == METHOD
        assert claim["available"] is True
    unavailable = by_budget[50]
    assert unavailable["claim_type"] == "unavailable_budget_curve_observation"
    assert unavailable["condition_id"] == condition_ids[50]
    assert unavailable["status"] == "unavailable"
    assert unavailable["value"] is None
    assert unavailable["labels_consumed"] == labels_by_budget[50]

    planned = ResultRenderer.ground_assistant_message(
        json.dumps({"template": "summary", "condition_refs": [condition_ids[0]]}),
        trace,
        [EXPERIMENT_ID],
        "Summarize one selected budget",
    )
    assert {claim["condition_id"] for claim in planned["claims"]} == {
        condition_ids[0], condition_ids[50],
    }
    assert "budget 50" in planned["summary"]
    assert "private-curve-marker" not in json.dumps(result.model_dump(mode="json"))
    assert "private-curve-marker" not in json.dumps(rendered)
    assert "private-curve-marker" not in json.dumps(planned)
