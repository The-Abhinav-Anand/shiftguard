"""Tripwires: the synthetic repeat slice must never reach data, scoring or a provider."""

from __future__ import annotations

import importlib

import pytest


_FORBIDDEN = (
    ("shiftguard.datasets.bank", "clean_bank_rows"),
    ("shiftguard.datasets.bank", "BankDataset.from_clean_csv"),
    ("shiftguard.datasets.bank", "BankDataset.from_synthetic_csv"),
    ("shiftguard.datasets.adult", "clean_adult_rows"),
    ("shiftguard.datasets.adult", "make_adult_role_splits"),
    ("shiftguard.datasets.adult", "acquire_adult_train_only"),
    ("shiftguard.datasets.adult", "execute_adult_confirmatory"),
    ("shiftguard.protocol.splits", "make_role_splits"),
    ("shiftguard.experiments.evaluator", "FinalTestEvaluator.__init__"),
    ("shiftguard.experiments.evaluator", "FinalTestEvaluator.score"),
    ("shiftguard.experiments.runner", "run_baseline"),
    ("shiftguard.experiments.outage_runner", "run_outage_recovery"),
    ("shiftguard.experiments.stress_runner", "prepare_stress_partitions"),
    ("shiftguard.experiments.stress_runner", "execute_stress_engine"),
    ("shiftguard.experiments.stress_runner", "run_stress_engine"),
    ("shiftguard.agent.provider", "AgentProvider.chat"),
    ("shiftguard.agent.provider", "ScriptedProvider.chat"),
)


@pytest.fixture(autouse=True)
def forbid_application_paths(monkeypatch):
    def tripwire(name):
        def raiser(*_args, **_kwargs):
            raise AssertionError(f"synthetic repeat test reached {name}")
        return raiser

    for module_name, dotted in _FORBIDDEN:
        owner = importlib.import_module(module_name)
        *parents, attribute = dotted.split(".")
        for parent in parents:
            owner = getattr(owner, parent)
        monkeypatch.setattr(owner, attribute, tripwire(f"{module_name}.{dotted}"))
