"""Fabricated Bank-shaped rows for the development adapter tests.

Everything is generated here from a fixed seed. No file under var/datasets and
no Adult artifact is read; the numbers are engineering fixtures, not findings.
"""

from __future__ import annotations

import hashlib

import numpy as np

from shiftguard.datasets.bank import BANK_FEATURES, BankDataset, hash_clean_rows
from shiftguard.repeats.development_adapter import (
    plan_development_repeats,
    prepare_outer,
    execute_coordinate,
)
from shiftguard.repeats.models import (
    BANK_DEVELOPMENT_MODE,
    RepeatSpec,
    SourceBinding,
    canonical_digest,
)


ROW_COUNT = 2200  # the legacy 10% pool then holds 220 rows, above the 200-row grid maximum
FIXTURE_SEED = 20261014


def fake_digest(label: str) -> str:
    return hashlib.sha256(f"synthetic-adapter:{label}".encode("ascii")).hexdigest()


def fabricated_bank_dataset(row_count: int = ROW_COUNT, seed: int = FIXTURE_SEED) -> BankDataset:
    """Ten Bank features as strings plus a binary label; duplicates and conflicts occur."""
    rng = np.random.default_rng(seed)
    jobs = ("admin.", "blue-collar", "technician", "services", "retired", "unknown")
    marital = ("married", "single", "divorced")
    education = ("basic.9y", "high.school", "university.degree")
    flags = ("no", "yes", "unknown")
    outcomes = ("nonexistent", "failure", "success")

    bases = []
    for _ in range(500):
        previous = int(rng.choice((0, 0, 0, 1, 2)))
        outcome = "nonexistent" if previous == 0 else str(rng.choice(outcomes[1:]))
        bases.append({
            "age": str(int(rng.choice((22, 28, 34, 41, 47, 55, 63)))),
            "job": str(rng.choice(jobs, p=(0.3, 0.25, 0.2, 0.1, 0.1, 0.05))),
            "marital": str(rng.choice(marital, p=(0.55, 0.3, 0.15))),
            "education": str(rng.choice(education)),
            "default": str(rng.choice(flags, p=(0.8, 0.05, 0.15))),
            "housing": str(rng.choice(flags, p=(0.45, 0.5, 0.05))),
            "loan": str(rng.choice(flags, p=(0.8, 0.15, 0.05))),
            "pdays": "999" if previous == 0 else str(int(rng.choice((3, 6, 12)))),
            "previous": str(previous),
            "poutcome": outcome,
        })
    # Skewed base choice makes some exact-feature groups large; labels stay row-specific.
    weights = 1.0 / (np.arange(len(bases)) + 3.0)
    weights /= weights.sum()
    rows = []
    for row_id in range(1, row_count + 1):
        base = bases[int(rng.choice(len(bases), p=weights))]
        logit = (
            -1.7 + 1.9 * (base["poutcome"] == "success") + 0.8 * (int(base["previous"]) > 0)
            + 0.6 * (base["job"] == "retired") + 0.015 * (int(base["age"]) - 40)
        )
        label = int(rng.random() < 1.0 / (1.0 + np.exp(-logit)))
        rows.append({"row_id": row_id, **{name: base[name] for name in BANK_FEATURES}, "y": label})
    return BankDataset(rows, raw_hash=fake_digest("raw"), clean_hash=fake_digest("clean"))


def fabricated_binding(dataset: BankDataset, **overrides) -> SourceBinding:
    values = {
        "dataset": "synthetic-bank-shape",
        "release": "fabricated-v1",
        "raw_sha256": dataset.raw_hash,
        "clean_sha256": dataset.clean_hash,
        "feature_schema_sha256": canonical_digest(["synthetic-bank-schema", list(BANK_FEATURES)]),
        "group_manifest_sha256": fake_digest("group-manifest"),
        "source_sha256": fake_digest("source"),
        "dependency_lock_sha256": fake_digest("dependency-lock"),
        "protocol_review_sha256": fake_digest("protocol-review"),
        "exposure_status": "synthetic_fabricated",
    }
    values.update(overrides)
    return SourceBinding(**values)


def pin_verified_bank(monkeypatch, binding: SourceBinding) -> None:
    """Make the fabricated binding stand in for the verified Bank release (tests only)."""
    from shiftguard.repeats import planning

    monkeypatch.setattr(planning, "VERIFIED_BANK_DATASET", binding.dataset)
    monkeypatch.setattr(planning, "VERIFIED_BANK_RELEASE", binding.release)
    monkeypatch.setattr(planning, "VERIFIED_BANK_RAW_SHA256", binding.raw_sha256)
    monkeypatch.setattr(planning, "VERIFIED_BANK_CLEAN_SHA256", binding.clean_sha256)


def development_standin_dataset() -> BankDataset:
    """Fabricated rows with their true canonical clean hash and a raw digest of their own."""
    rows = fabricated_bank_dataset().rows
    return BankDataset(rows, raw_hash=fake_digest("dev-raw"), clean_hash=hash_clean_rows(rows))


def development_standin_binding(dataset: BankDataset, **overrides) -> SourceBinding:
    """A development_exposed binding with names and digests distinct from the synthetic lab's."""
    import dataclasses

    return dataclasses.replace(
        fabricated_binding(dataset, **overrides), dataset="dev-standin-bank",
        release="dev-standin-v1", exposure_status="development_exposed")


class Lab:
    """Caches the expensive pure steps so tests share one plan and one fit per outer."""

    def __init__(self, dataset: BankDataset | None = None, development: bool = False) -> None:
        self.dataset = fabricated_bank_dataset() if dataset is None else dataset
        if development:
            self.binding = development_standin_binding(self.dataset)
            self.spec = RepeatSpec(execution_mode=BANK_DEVELOPMENT_MODE)
        else:
            self.binding = fabricated_binding(self.dataset)
            self.spec = RepeatSpec()
        self.plan = plan_development_repeats(self.dataset, self.binding, self.spec)
        self._prepared: dict[int, object] = {}
        self._results: dict[tuple, object] = {}

    def prepared(self, outer_seed: int):
        if outer_seed not in self._prepared:
            self._prepared[outer_seed] = prepare_outer(self.dataset, self.plan, outer_seed)
        return self._prepared[outer_seed]

    def run(self, outer_seed: int, inner_id: int, **scope):
        key = (outer_seed, inner_id, tuple(sorted(scope.items())))
        if key not in self._results:
            self._results[key] = execute_coordinate(self.prepared(outer_seed), inner_id, **scope)
        return self._results[key]
