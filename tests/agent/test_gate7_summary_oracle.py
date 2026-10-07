"""Renderer mutations must be rejected by the real Gate 7 campaign assertion."""

from __future__ import annotations

import copy

import pytest

from shiftguard.agent.rendering import ResultRenderer
from test_gate7_adversarial_campaign import (
    MATRIX,
    campaign_sqlite,
    test_gate7_public_regression as _campaign_assertion_test,
)


SUMMARY_CASE = next(case for case in MATRIX["cases"] if case["id"] == "positive-deterministic-summary")


class _CampaignRequest:
    def __init__(self, database):
        self.database = database

    def getfixturevalue(self, name):
        assert name == "campaign_sqlite"
        return self.database


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param(None, id="valid-positive"),
        pytest.param("wrong_value", id="wrong-value"),
        pytest.param("absent_claim", id="absent-claim"),
        pytest.param("wrong_condition_id", id="wrong-condition-id"),
        pytest.param("wrong_condition_key", id="wrong-condition-key"),
        pytest.param("wrong_experiment_id", id="wrong-experiment-id"),
    ],
)
def test_campaign_summary_assertion_rejects_renderer_mutations(
    mutation, campaign_sqlite, tmp_path, monkeypatch,
):
    original_renderer = ResultRenderer.render_from_tool_results
    returned = []

    def render_with_mutation(prompt, tool_trace, evidence_refs):
        response = original_renderer(prompt, tool_trace, evidence_refs)
        if mutation is not None:
            claim = response["claims"][0]
            if mutation == "wrong_value":
                claim["value"] = 0.98765
            elif mutation == "absent_claim":
                response["claims"] = []
            elif mutation == "wrong_condition_id":
                claim["condition_id"] = "0" * 24
            elif mutation == "wrong_condition_key":
                claim["condition_key"] = "logistic_regression__mcar_0_30__b50__raw"
            elif mutation == "wrong_experiment_id":
                claim["experiment_id"] = "f" * 24
            else:
                pytest.fail(f"unaccounted summary mutation: {mutation}")
        returned.append(copy.deepcopy(response))
        return response

    monkeypatch.setattr(ResultRenderer, "render_from_tool_results", staticmethod(render_with_mutation))
    request = _CampaignRequest(campaign_sqlite)

    if mutation is None:
        _campaign_assertion_test(SUMMARY_CASE, "sqlite", request, tmp_path)
        assert len(returned) == 1
        return

    with pytest.raises(AssertionError):
        _campaign_assertion_test(SUMMARY_CASE, "sqlite", request, tmp_path)
    assert len(returned) == 1
    assert returned[0]["claims"] != [{
        "claim_type": "best_calibrator_summary",
        "description": "Best Brier score: 0.1000",
        "metric_name": "brier_score",
        "value": 0.1,
        "condition_key": "logistic_regression__mcar_0_30__b50__target_temperature",
        "condition_id": campaign_sqlite.condition_ids["target_temperature"],
        "experiment_id": campaign_sqlite.experiment_id,
    }]
