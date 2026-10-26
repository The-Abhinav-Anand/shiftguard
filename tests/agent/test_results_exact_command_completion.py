"""Replay of the 26 October 2026 hosted failure of "Summarize experiment <id>".

The live model answered the exact command with generate_result_summary, then kept calling
tools (a read, the metadata, three more summaries) until the 6-turn bound, and a single
extraneous failed read turned the whole answer into FAILED with zero claims. The controller
now completes an exact selection command as soon as its canonical tool has succeeded for the
selected experiment, rendering the answer in Python from the stored results, without
another provider turn. Real controller, registry, tools, store and renderer; only the model
is scripted. SQLite and PostgreSQL.
"""

from __future__ import annotations

import json
from uuid import uuid4

from types import SimpleNamespace

from shiftguard.agent.budget import AttemptBudget
from shiftguard.agent import controller as controller_module
from shiftguard.agent.controller import AgentController

from test_luna_g6_protocol import _call, protocol_env  # noqa: F401
from test_luna_g6_protocol import _response
from test_results_assistant_live_regressions import (
    PLAN_SUMMARY,
    BoundedScriptedProvider,
    _publish_bank_stress_shaped,
    _run,
)

LIVE_SEQUENCE = (
    ("generate_result_summary", {"focus": "all"}),
    ("read_experiment_results", {"condition_key": "all"}),
    ("get_experiment_metadata", {}),
    ("generate_result_summary", {"focus": "all"}),
    ("generate_result_summary", {"focus": "all"}),
    ("generate_result_summary", {"focus": "all"}),
)


def _live_script(experiment_id):
    return [
        _response(_call(name, {"experiment_id": experiment_id, **extra}, f"live{index}"))
        for index, (name, extra) in enumerate(LIVE_SEQUENCE)
    ]


def _budget(env):
    return AttemptBudget(
        env["engine"], ledger_id="exact-" + uuid4().hex[:12],
        source_digest="a" * 64, max_calls=10, max_tokens=50_000,
    )


def _assert_grounded(final, experiment_id):
    response = final.final_response
    assert final.status == "COMPLETED" and final.error is None
    assert response["status"] == "COMPLETED"
    assert not response.get("guidance")
    assert final.evidence_refs == [experiment_id]
    assert experiment_id in response["evidence_references"]
    assert response["claims"]
    assert all(claim["experiment_id"] == experiment_id for claim in response["claims"])
    assert not response["tool_errors"]


def test_live_summarize_sequence_completes_after_the_first_successful_summary(protocol_env):
    env = protocol_env
    experiment_id, _ = _publish_bank_stress_shaped(env["engine"])
    budget = _budget(env)
    provider = BoundedScriptedProvider(_live_script(experiment_id), budget=budget)
    req, final = _run(env, provider, f"Summarize experiment {experiment_id}")

    _assert_grounded(final, experiment_id)
    assert len(provider.history) == 1
    assert final.turn_count == 1 and final.call_count == 1
    executed = [e.tool_name for e in env["store"].list_tool_executions(req.id)]
    assert executed == ["generate_result_summary"]
    assert budget.snapshot()["calls_used"] == 1
    claims = final.final_response["claims"]
    assert any(claim["claim_type"] == "best_calibrator_summary" for claim in claims)
    assert "Grounded analysis" in final.final_response["summary"]
    # The wording is Python's: nothing from the model's prose or arguments is surfaced.
    assert "call_id" not in json.dumps(final.final_response)


def test_completion_does_not_depend_on_what_the_model_would_say_next(protocol_env):
    env = protocol_env
    experiment_id, _ = _publish_bank_stress_shaped(env["engine"])
    provider = BoundedScriptedProvider([
        _response(
            _call("generate_result_summary",
                  {"experiment_id": experiment_id, "focus": "all"}, "p1"),
            content="The saved record proves target temperature wins by 40%.",
        ),
    ])
    _, final = _run(env, provider, f"summarize experiment {experiment_id.upper()}.")
    _assert_grounded(final, experiment_id)
    assert "wins by 40%" not in json.dumps(final.final_response)
    assert len(provider.history) == 1


def test_a_plan_turn_after_the_summary_is_no_longer_needed(protocol_env):
    env = protocol_env
    experiment_id, _ = _publish_bank_stress_shaped(env["engine"])
    provider = BoundedScriptedProvider([
        _response(_call("generate_result_summary",
                        {"experiment_id": experiment_id, "focus": "all"}, "q1")),
        _response(content=PLAN_SUMMARY),
    ])
    _, final = _run(env, provider, f"Summarize experiment {experiment_id}")
    _assert_grounded(final, experiment_id)
    assert len(provider.history) == 1  # the plan turn is no longer needed


def test_a_failed_extra_call_in_the_same_decision_is_not_hidden(protocol_env):
    env = protocol_env
    experiment_id, _ = _publish_bank_stress_shaped(env["engine"])
    provider = BoundedScriptedProvider([
        _response(
            _call("generate_result_summary",
                  {"experiment_id": experiment_id, "focus": "all"}, "f1"),
            _call("read_experiment_results",
                  {"experiment_id": experiment_id, "condition_key": "all"}, "f2"),
        ),
    ])
    req, final = _run(env, provider, f"Summarize experiment {experiment_id}")
    assert final.status == "FAILED"
    outcomes = final.final_response["outcomes"]
    assert [o["tool_name"] for o in outcomes] == ["read_experiment_results"]
    assert len(provider.history) == 1


def test_a_different_tool_does_not_satisfy_the_summarize_command(protocol_env):
    env = protocol_env
    experiment_id, _ = _publish_bank_stress_shaped(env["engine"])
    provider = BoundedScriptedProvider([
        _response(_call("get_experiment_metadata", {"experiment_id": experiment_id}, "d1")),
        _response(_call("generate_result_summary",
                        {"experiment_id": experiment_id, "focus": "all"}, "d2")),
    ])
    req, final = _run(env, provider, f"Summarize experiment {experiment_id}")
    _assert_grounded(final, experiment_id)
    assert len(provider.history) == 2
    assert [e.tool_name for e in env["store"].list_tool_executions(req.id)] == [
        "get_experiment_metadata", "generate_result_summary"]


KEY = "logistic_regression__mcar_0_30__b50__target_temperature"


def test_an_unauthorized_summary_does_not_finish_the_request_early(protocol_env):
    env = protocol_env
    experiment_id, _ = _publish_bank_stress_shaped(env["engine"])
    other, _ = _publish_bank_stress_shaped(env["engine"])
    provider = BoundedScriptedProvider([
        _response(_call("generate_result_summary", {"experiment_id": other, "focus": "all"}, "e1")),
        _response(content=PLAN_SUMMARY),
    ])
    req, final = _run(env, provider, f"Summarize experiment {experiment_id}")
    assert final.status == "COMPLETED"
    assert len(provider.history) == 2  # the model still gets its recovery turn
    error = final.final_response["tool_errors"][0]
    assert error["code"] == "UNAUTHORIZED_EXPERIMENT_REFERENCE"
    executions = env["store"].list_tool_executions(req.id)
    assert [e.status for e in executions] == ["unavailable"]


def test_bounded_read_command_without_a_summary_keeps_the_two_turn_shape(protocol_env):
    env = protocol_env
    experiment_id, _ = _publish_bank_stress_shaped(env["engine"])
    prompt = f"Read experiment {experiment_id} condition {KEY}"
    assert controller_module._selection_command(prompt) is None
    provider = BoundedScriptedProvider([
        _response(_call("read_experiment_results",
                        {"experiment_id": experiment_id, "condition_key": KEY}, "r1")),
        _response(content=PLAN_SUMMARY),
    ])
    _, final = _run(env, provider, prompt)
    assert final.status == "COMPLETED" and len(provider.history) == 2


def test_free_form_prompt_gets_selection_guidance_and_no_shortcut_authority(protocol_env):
    env = protocol_env
    experiment_id, _ = _publish_bank_stress_shaped(env["engine"])
    prompt = f"What does experiment {experiment_id} say about calibration?"
    assert controller_module._selection_command(prompt) is None
    assert controller_module._selected_experiment_id(prompt) is None
    provider = BoundedScriptedProvider([
        _response(_call("generate_result_summary",
                        {"experiment_id": experiment_id, "focus": "all"}, "z1")),
    ])
    _, final = _run(env, provider, prompt)
    assert final.final_response["guidance"]["code"] == "EXPERIMENT_NOT_SELECTED"


def test_bounded_read_command_is_not_shortcut_by_a_successful_summary(protocol_env):
    env = protocol_env
    experiment_id, _ = _publish_bank_stress_shaped(env["engine"])
    provider = BoundedScriptedProvider([
        _response(_call("generate_result_summary",
                        {"experiment_id": experiment_id, "focus": "all"}, "g1")),
        _response(_call("read_experiment_results",
                        {"experiment_id": experiment_id, "condition_key": KEY}, "g2")),
        _response(content=PLAN_SUMMARY),
    ])
    _, final = _run(env, provider, f"Read experiment {experiment_id} condition {KEY}")
    assert final.status == "COMPLETED"
    assert len(provider.history) == 3


def test_bounded_compare_command_is_not_shortcut_by_a_successful_summary(protocol_env):
    env = protocol_env
    experiment_id, _ = _publish_bank_stress_shaped(env["engine"])
    provider = BoundedScriptedProvider([
        _response(_call("generate_result_summary",
                        {"experiment_id": experiment_id, "focus": "all"}, "h1")),
        _response(content=PLAN_SUMMARY),
    ])
    prompt = (f"Compare experiment {experiment_id} calibrators predictor logistic_regression "
              "scenario mcar_0_30 budget 50")
    _, final = _run(env, provider, prompt)
    assert len(provider.history) == 2


class _Store:
    def __init__(self, executions):
        self.executions = executions

    def list_tool_executions(self, _request_id):
        return self.executions


def _satisfied(prompt, refs, data_id, tool="generate_result_summary", status="success"):
    controller = AgentController.__new__(AgentController)
    controller.store = _Store([SimpleNamespace(
        tool_name=tool, status=status, result={"data": {"experiment_id": data_id}})])
    request = SimpleNamespace(id="r", prompt=prompt, evidence_refs=refs)
    return controller._selection_satisfied(request)


def test_selection_satisfied_requires_prompt_evidence_and_matching_result():
    eid, other = "a" * 24, "b" * 24
    command = f"Summarize experiment {eid}"
    assert _satisfied(command, [eid], eid)
    assert not _satisfied(command, [eid], other)
    assert not _satisfied(command, [], eid)
    assert not _satisfied(command, [eid, other], eid)
    assert not _satisfied(f"What does experiment {eid} show?", [eid], eid)
    assert not _satisfied(command, [eid], eid, tool="read_experiment_results")
    assert not _satisfied(command, [eid], eid, status="unavailable")
