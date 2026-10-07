"""Tests for Gate 6 static tool registry, strict schemas, and dispatch rules."""

from __future__ import annotations

import json
import pytest
from sqlalchemy import create_engine

from shiftguard.agent.policy import AgentErrorCode, APPROVED_PRESETS, SUPPORTED_COST_PAIRS
from shiftguard.agent.registry import ToolRegistry
from shiftguard.agent.tools import ToolContext
from shiftguard.settings import Settings


EXPECTED_TWELVE_TOOLS = [
    "calculate_decision_loss",
    "compare_calibrators",
    "compare_outages",
    "generate_result_summary",
    "get_experiment_metadata",
    "get_label_budget_curve",
    "inspect_dataset",
    "inspect_missingness",
    "list_available_scenarios",
    "read_experiment_results",
    "run_experiment",
    "run_stress_suite",
]


@pytest.fixture
def registry() -> ToolRegistry:
    return ToolRegistry()


@pytest.fixture
def tool_context(tmp_path) -> ToolContext:
    engine = create_engine(f"sqlite:///{tmp_path}/test_tools.db")
    settings = Settings(SHIFTGUARD_DB_URL=f"sqlite:///{tmp_path}/test_tools.db")
    return ToolContext(
        engine=engine,
        settings=settings,
        session_id="test-session-001",
        request_id="test-req-001",
        ordinal=1,
    )


def test_exact_twelve_tools_registered(registry: ToolRegistry):
    names = registry.get_tool_names()
    assert names == sorted(EXPECTED_TWELVE_TOOLS)
    assert len(names) == 12


def test_side_effect_classification(registry: ToolRegistry):
    for name in EXPECTED_TWELVE_TOOLS:
        is_side_effect = registry.is_side_effect(name)
        if name in ("run_experiment", "run_stress_suite"):
            assert is_side_effect is True, f"{name} must be declared as a side effect"
        else:
            assert is_side_effect is False, f"{name} must be declared as read-only"


def test_unknown_tool_rejection(registry: ToolRegistry, tool_context: ToolContext):
    res = registry.dispatch("drop_database", "{}", tool_context, "call_1")
    assert res.status == "error"
    assert AgentErrorCode.TOOL_NOT_FOUND in (res.error or "")


def test_invalid_json_arguments_rejection(registry: ToolRegistry, tool_context: ToolContext):
    res = registry.dispatch("inspect_dataset", "not-valid-json", tool_context, "call_2")
    assert res.status == "error"
    assert AgentErrorCode.INVALID_ARGUMENTS in (res.error or "")


def test_extra_fields_forbidden(registry: ToolRegistry, tool_context: ToolContext):
    # StrictSchema forbids extra fields
    payload = json.dumps({"dataset_id": "bank", "extra_field": 123})
    res = registry.dispatch("inspect_dataset", payload, tool_context, "call_3")
    assert res.status == "error"
    assert AgentErrorCode.INVALID_ARGUMENTS in (res.error or "")


def test_inspect_missingness_requires_single_selector(registry: ToolRegistry, tool_context: ToolContext):
    # Both scenario and experiment_id -> Rejected
    both_payload = json.dumps({"scenario": "mcar_0_30", "experiment_id": "exp_12345"})
    res_both = registry.dispatch("inspect_missingness", both_payload, tool_context, "call_4")
    assert res_both.status == "error"
    assert "Exactly one" in (res_both.error or "")

    # Neither scenario nor experiment_id -> Rejected
    neither_payload = json.dumps({})
    res_neither = registry.dispatch("inspect_missingness", neither_payload, tool_context, "call_5")
    assert res_neither.status == "error"


def test_unsupported_dataset_rejected(registry: ToolRegistry, tool_context: ToolContext):
    payload = json.dumps({"dataset_id": "adult_census"})
    res = registry.dispatch("inspect_dataset", payload, tool_context, "call_6")
    assert res.status == "unavailable"
    assert "unsupported" in (res.error or "").lower()


def test_calculate_decision_loss_unsupported_cost_pair(registry: ToolRegistry, tool_context: ToolContext):
    # Arbitrary cost pair outside the predeclared grid
    payload = json.dumps({
        "experiment_id": "exp_test",
        "scenario": "mcar_0_30",
        "predictor": "logistic_regression",
        "method": "source_fraction_binned_temperature",
        "fp_cost": 2.5,
        "fn_cost": 7.5,
    })
    res = registry.dispatch("calculate_decision_loss", payload, tool_context, "call_7")
    assert res.status == "error"
    assert AgentErrorCode.UNSUPPORTED_COST_PAIR in (res.error or "")


def test_openai_tool_definitions_generated(registry: ToolRegistry):
    defs = registry.get_openai_tool_definitions()
    assert len(defs) == 12
    for td in defs:
        assert td["type"] == "function"
        fn = td["function"]
        assert fn["name"] in EXPECTED_TWELVE_TOOLS
        assert "description" in fn
        assert "parameters" in fn
        assert fn["parameters"].get("type") == "object"
