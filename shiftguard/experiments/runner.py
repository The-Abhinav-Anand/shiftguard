from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import subprocess
from uuid import uuid4

import numpy as np

from shiftguard.datasets.bank import BankDataset
from shiftguard.experiments.artifacts import write_json_artifact
from shiftguard.experiments.config import BaselineConfig
from shiftguard.experiments.evaluator import FinalTestEvaluator
from shiftguard.experiments.ids import stable_hash
from shiftguard.predictors.logistic import fit_initial_logistic_regression, predictor_identity
from shiftguard.preprocessing.tabular import feature_rows, fit_train_preprocessor, preprocessing_config
from shiftguard.protocol.splits import make_role_splits
from shiftguard.storage.repositories import ExperimentRepository


@dataclass(frozen=True)
class BaselineResult:
    experiment_id: str
    execution_id: str
    metrics: dict[str, object]
    content_hashes: dict[str, str]
    artifact_dir: Path


@dataclass(frozen=True)
class PreparedBaselineHandoff:
    train_features: tuple[dict[str, str | int], ...]
    train_labels: tuple[int, ...]
    source_cal_features: tuple[dict[str, str | int], ...]
    target_pool_features: tuple[dict[str, str | int], ...]
    final_features: tuple[dict[str, str | int], ...]
    evaluator: FinalTestEvaluator
    roles: dict[str, tuple[int, ...]]
    raw_hash: str
    clean_hash: str


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def audit_provenance() -> dict[str, object]:
    git = ["git", "-c", f"safe.directory={REPOSITORY_ROOT.as_posix()}"]
    try:
        result = subprocess.run([*git, "rev-parse", "HEAD"], cwd=REPOSITORY_ROOT, capture_output=True, text=True, check=False)
        status = subprocess.run([*git, "status", "--porcelain"], cwd=REPOSITORY_ROOT, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        git_provenance = {"available": False, "head": None, "dirty": None}
    else:
        git_provenance = {"available": True, "head": result.stdout.strip() if result.returncode == 0 else None, "dirty": bool(status.stdout.strip()) if status.returncode == 0 else None}
    lockfile = REPOSITORY_ROOT / "uv.lock"
    return {"git": git_provenance, "lockfile": {"path": "uv.lock", "sha256": hashlib.sha256(lockfile.read_bytes()).hexdigest()}}


def _seed_bundle(master_seed: int) -> dict[str, int]:
    names = ("split", "model", "mask", "acquisition")
    children = np.random.SeedSequence(master_seed).spawn(4)
    return {name: int(child.generate_state(1)[0]) for name, child in zip(names, children, strict=True)}


def prepare_baseline_handoff(dataset: BankDataset, config: BaselineConfig) -> PreparedBaselineHandoff:
    seeds = _seed_bundle(config.master_seed)
    roles = make_role_splits(dataset.rows, seeds["split"])
    rows_by_id = {int(row["row_id"]): row for row in dataset.rows}
    train_rows = [rows_by_id[row_id] for row_id in roles["train"]]
    source_rows = [rows_by_id[row_id] for row_id in roles["source_cal"]]
    pool_rows = [rows_by_id[row_id] for row_id in roles["target_pool"]]
    final_rows = [rows_by_id[row_id] for row_id in roles["final_test"]]
    return PreparedBaselineHandoff(train_features=tuple(feature_rows(train_rows)), train_labels=tuple(int(row["y"]) for row in train_rows), source_cal_features=tuple(feature_rows(source_rows)), target_pool_features=tuple(feature_rows(pool_rows)), final_features=tuple(feature_rows(final_rows)), evaluator=FinalTestEvaluator(tuple(int(row["y"]) for row in final_rows)), roles=roles, raw_hash=dataset.raw_hash, clean_hash=dataset.clean_hash)


def run_baseline(handoff: PreparedBaselineHandoff, config: BaselineConfig, database_url: str) -> BaselineResult:
    seeds = _seed_bundle(config.master_seed)
    train_features = list(handoff.train_features)
    final_features = list(handoff.final_features)
    preprocessor = fit_train_preprocessor(train_features)
    model = fit_initial_logistic_regression(preprocessor.transform(train_features), list(handoff.train_labels), seeds["model"])
    probabilities = model.predict_proba(preprocessor.transform(final_features))[:, 1].tolist()
    metrics = handoff.evaluator.score(probabilities)
    split_hash = stable_hash(handoff.roles)
    metadata = {"preprocessing": preprocessing_config(), "predictor": predictor_identity(model)}
    deterministic_payload = {"config": config.to_dict(), "seeds": seeds, "dataset": {"raw_hash": handoff.raw_hash, "clean_hash": handoff.clean_hash}, "split_hash": split_hash, "metrics": metrics, "metadata": metadata, "protocol": {"duplicate_policy": "retain duplicate source rows and split by stable row_id", "final_labels_scope": "evaluator only", "lock_provenance": "unlocked-development"}}
    experiment_id = stable_hash(deterministic_payload)[:24]
    artifact_dir = config.artifact_root / experiment_id
    content_hashes = {"config": write_json_artifact(artifact_dir, "config.json", config.to_dict()), "seeds": write_json_artifact(artifact_dir, "seeds.json", seeds), "splits": write_json_artifact(artifact_dir, "splits.json", handoff.roles), "metadata": write_json_artifact(artifact_dir, "metadata.json", metadata), "result": write_json_artifact(artifact_dir, "result.json", metrics), "logical_content": stable_hash(deterministic_payload)}
    execution_id = str(uuid4())
    audit_metadata = {"execution_id": execution_id, "provenance": audit_provenance()}
    repository = ExperimentRepository.from_url(database_url)
    try:
        repository.put(experiment_id, deterministic_payload, content_hashes, execution_id, audit_metadata)
    finally:
        repository.dispose()
    return BaselineResult(experiment_id=experiment_id, execution_id=execution_id, metrics=metrics, content_hashes=content_hashes, artifact_dir=artifact_dir)
