from __future__ import annotations

import json
from pathlib import Path

import pytest
from sklearn.metrics import brier_score_loss

from shiftguard.datasets.bank import BANK_FEATURES, BankDataset, FROZEN_BANK_SOURCE, clean_bank_rows, write_clean_csv
from shiftguard.experiments.config import BaselineConfig, DEVELOPMENT_SEEDS, load_baseline_config
from shiftguard.metrics.probability import brier_score, log_loss
from shiftguard.metrics.reliability import reliability_bins
from shiftguard.protocol.splits import make_role_splits
import shiftguard.experiments.runner as runner
from shiftguard.experiments.runner import audit_provenance


def test_bank_source_manifest_freezes_official_hashes() -> None:
    manifest = json.loads((Path(__file__).parents[2] / "data/manifests/bank.json").read_text(encoding="utf-8"))

    assert manifest["archive_sha256"] == "e0bf5f5de5b846e2f18e9d90606637267d46dfa260e0f17bb12e605db5efbeb4"
    assert manifest["raw_member"] == "bank-additional/bank-additional-full.csv"
    assert manifest["raw_member_sha256"] == "74adfc578bf77a7ff4bb1ba4a9f8709d9e3c6907342959c2c8416847e0afb4d8"


def test_gate1_config_freezes_features_fractions_and_development_seed() -> None:
    config = BaselineConfig(master_seed=31001)

    assert config.features == BANK_FEATURES
    assert config.role_fractions == {"train": 0.55, "source_cal": 0.15, "target_pool": 0.10, "final_test": 0.20}
    assert config.master_seed in DEVELOPMENT_SEEDS


@pytest.mark.parametrize(
    "payload",
    [
        {"master_seed": 999},
        {"master_seed": 31001, "features": ("age",)},
        {"master_seed": 31001, "role_fractions": {"train": 1.0}},
    ],
)
def test_gate1_config_rejects_invalid_contracts(payload: dict) -> None:
    with pytest.raises(ValueError):
        BaselineConfig(**payload)


def test_bank_baseline_yaml_config_loads(tmp_path) -> None:
    config_path = tmp_path / "bank-baseline.yaml"
    config_path.write_text("master_seed: 31001\n", encoding="utf-8")

    assert load_baseline_config(config_path) == BaselineConfig(master_seed=31001)


def test_bank_cleaning_keeps_exact_features_and_sentinels() -> None:
    raw = {
        "age": "42", "job": "admin.", "marital": "single", "education": "unknown",
        "default": "no", "housing": "yes", "loan": "no", "pdays": "999",
        "previous": "0", "poutcome": "nonexistent", "duration": "120", "y": "yes",
    }

    rows = clean_bank_rows([raw])

    assert rows == [{"row_id": 1, **{name: raw[name] for name in BANK_FEATURES}, "y": 1}]


def test_clean_csv_rejects_duplicate_ids_and_mismatched_frozen_source(tmp_path) -> None:
    rows = [
        {"row_id": 1, "age": "30", "job": "admin.", "marital": "single", "education": "secondary", "default": "no", "housing": "yes", "loan": "no", "pdays": "999", "previous": "0", "poutcome": "nonexistent", "y": 0},
        {"row_id": 1, "age": "31", "job": "technician", "marital": "married", "education": "tertiary", "default": "no", "housing": "no", "loan": "no", "pdays": "999", "previous": "0", "poutcome": "nonexistent", "y": 1},
    ]
    path = tmp_path / "bank.csv"
    clean_hash = write_clean_csv(rows, path)
    manifest = {**FROZEN_BANK_SOURCE, "clean_sha256": clean_hash, "rows": len(rows)}

    with pytest.raises(ValueError, match="unique"):
        BankDataset.from_clean_csv(path, manifest, allow_synthetic=True)

    valid_rows = [rows[0]]
    clean_hash = write_clean_csv(valid_rows, path)
    bad_manifest = {**FROZEN_BANK_SOURCE, "source_url": "https://invalid.example/bank.zip", "clean_sha256": clean_hash, "rows": len(valid_rows)}
    with pytest.raises(ValueError, match="frozen source identity"):
        BankDataset.from_clean_csv(path, bad_manifest, allow_synthetic=True)


def test_fabricated_clean_csv_rejected_by_production_loader(tmp_path) -> None:
    valid_rows = [{"row_id": 1, "age": "30", "job": "admin.", "marital": "single", "education": "secondary", "default": "no", "housing": "yes", "loan": "no", "pdays": "999", "previous": "0", "poutcome": "nonexistent", "y": 0}]
    path = tmp_path / "bank.csv"
    clean_hash = write_clean_csv(valid_rows, path)
    manifest = {**FROZEN_BANK_SOURCE, "clean_sha256": clean_hash, "rows": len(valid_rows)}
    with pytest.raises(ValueError, match="does not match frozen canonical digest"):
        BankDataset.from_clean_csv(path, manifest)


def test_role_splits_are_stable_disjoint_and_cover_all_rows() -> None:
    rows = [{"row_id": index, "y": index % 2} for index in range(1, 201)]

    first = make_role_splits(rows, split_seed=1234)
    second = make_role_splits(rows, split_seed=1234)

    assert first == second
    role_ids = [set(role) for role in first.values()]
    assert set.union(*role_ids) == set(range(1, 201))
    assert sum(map(len, role_ids)) == 200


@pytest.mark.parametrize(
    ("labels", "probabilities"),
    [
        ([0, 1], [1.0, 0.0]),
        ([0, 1, 1, 0], [0.1, 0.6, 0.8, 0.2]),
    ],
)
def test_brier_matches_pinned_sklearn_reference(labels: list[int], probabilities: list[float]) -> None:
    assert brier_score(labels, probabilities, scale_by_half=True) == pytest.approx(
        brier_score_loss(labels, probabilities, scale_by_half=True)
    )
    assert brier_score(labels, probabilities, scale_by_half=False) == pytest.approx(
        brier_score_loss(labels, probabilities, scale_by_half=False)
    )


def test_probability_metrics_match_declared_fixture() -> None:
    labels = [0, 1]
    probabilities = [0.25, 0.75]

    assert brier_score(labels, probabilities, scale_by_half=True) == pytest.approx(0.0625)
    assert log_loss(labels, probabilities, clip=1e-15) == pytest.approx(0.2876820724517809)
    bins = reliability_bins(labels, probabilities, bins=10)
    assert bins[2]["count"] == 1
    assert bins[7]["positive_fraction"] == 1.0
    assert bins[0] == {"lower": 0.0, "upper": 0.1, "count": 0, "mean_probability": None, "positive_fraction": None}


def test_audit_provenance_records_git_and_lockfile_state_outside_content_hashes() -> None:
    provenance = audit_provenance()

    assert set(provenance["git"]) == {"available", "head", "dirty"}
    assert provenance["lockfile"]["path"] == "uv.lock"
    assert len(provenance["lockfile"]["sha256"]) == 64


def test_audit_provenance_records_missing_git_without_aborting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError()))

    provenance = audit_provenance()

    assert provenance["git"] == {"available": False, "head": None, "dirty": None}
