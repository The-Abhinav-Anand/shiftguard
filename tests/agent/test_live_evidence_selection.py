from types import SimpleNamespace

import pytest

from shiftguard.agent.controller import AgentController
from shiftguard.agent.execution_authority import authorized_execution_presets


EXPERIMENT_ID = "a" * 24
CONDITION_KEY = "logistic_regression__history_block_0_50__b50__raw"
READ_PROMPT = f"Read experiment {EXPERIMENT_ID} condition {CONDITION_KEY}"
COMPARE_PROMPT = (
    f"Compare experiment {EXPERIMENT_ID} calibrators predictor logistic_regression "
    "scenario history_block_0_50 budget 50"
)


class _Store:
    def __init__(self, request):
        self.request = request
        self.updates = 0

    def update_request(self, request_id, generation, *, evidence_refs, worker_id):
        assert request_id == self.request.id
        self.request.evidence_refs = evidence_refs
        self.updates += 1
        return True

    def get_request(self, request_id):
        return self.request if request_id == self.request.id else None


def _bind(monkeypatch, prompt):
    request = SimpleNamespace(id="request-1", prompt=prompt, evidence_refs=[])
    store = _Store(request)

    class _Repository:
        def __init__(self, _engine):
            pass

        def get_published(self, experiment_id):
            return object() if experiment_id == EXPERIMENT_ID else None

    monkeypatch.setattr("shiftguard.agent.controller.ExperimentRepository", _Repository)
    controller = object.__new__(AgentController)
    controller.engine = object()
    controller.store = store
    result = controller._bind_selected_publications(request, 1, "worker-1")
    return result, store


@pytest.mark.parametrize("prompt", [READ_PROMPT, COMPARE_PROMPT])
def test_typed_bounded_selection_binds_only_the_named_published_experiment(monkeypatch, prompt):
    request, store = _bind(monkeypatch, prompt)
    assert request.evidence_refs == [EXPERIMENT_ID]
    assert store.updates == 1


@pytest.mark.parametrize(
    "prompt",
    [
        f"Read the results of published experiment {EXPERIMENT_ID}.",
        f"Compare experiment {EXPERIMENT_ID}",
    ],
)
def test_existing_standard_experiment_selectors_remain_supported(monkeypatch, prompt):
    request, store = _bind(monkeypatch, prompt)
    assert request.evidence_refs == [EXPERIMENT_ID]
    assert store.updates == 1


@pytest.mark.parametrize(
    "prompt",
    [
        f'"{READ_PROMPT}"',
        f"{READ_PROMPT} and run bank-stress",
        f"{COMPARE_PROMPT} then Run bank-stress",
        f"Read experiment {EXPERIMENT_ID} condition unknown__history_block_0_50__b50__raw",
        f"Read experiment {EXPERIMENT_ID} condition {CONDITION_KEY} extra",
        f"Compare experiment {EXPERIMENT_ID} calibrators predictor logistic_regression scenario history_block_0_50 budget 999",
        "Run bank-stress and read experiment " + EXPERIMENT_ID + " condition " + CONDITION_KEY,
    ],
)
def test_quoted_unsupported_or_appended_commands_bind_no_evidence_or_run_grant(monkeypatch, prompt):
    request, store = _bind(monkeypatch, prompt)
    assert request.evidence_refs == []
    assert store.updates == 0
    assert authorized_execution_presets(prompt) == frozenset()
