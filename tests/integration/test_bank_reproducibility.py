from __future__ import annotations

import hashlib

from shiftguard.datasets.bank import BankDataset
from shiftguard.experiments.config import BaselineConfig
from shiftguard.experiments.runner import prepare_baseline_handoff, run_baseline
from shiftguard.storage.repositories import ExperimentRepository


def test_fixed_config_reproduces_metrics_content_hashes_and_db_reopen(tmp_path) -> None:
    rows = []
    for row_id in range(1, 101):
        rows.append({
            "row_id": row_id, "age": str(20 + row_id % 40), "job": "admin." if row_id % 2 else "technician",
            "marital": "single", "education": "secondary", "default": "no", "housing": "yes",
            "loan": "no", "pdays": "999", "previous": "0", "poutcome": "nonexistent", "y": row_id % 2,
        })
    dataset = BankDataset(rows=rows, raw_hash="raw-fixture", clean_hash="clean-fixture")
    config = BaselineConfig(master_seed=31001, artifact_root=tmp_path / "artifacts")
    database_url = f"sqlite:///{tmp_path / 'gate1.db'}"

    first = run_baseline(prepare_baseline_handoff(dataset, config), config, database_url)
    second = run_baseline(prepare_baseline_handoff(dataset, config), config, database_url)

    assert first.metrics == second.metrics
    assert first.content_hashes == second.content_hashes
    assert first.execution_id != second.execution_id
    assert first.content_hashes["logical_content"] != first.content_hashes["result"]
    for name in ("config", "seeds", "splits", "metadata", "result"):
        artifact_bytes = (first.artifact_dir / f"{name}.json").read_bytes()
        assert artifact_bytes.endswith(b"\n")
        assert b"\r\n" not in artifact_bytes
        assert first.content_hashes[name] == hashlib.sha256(artifact_bytes).hexdigest()
    repository = ExperimentRepository.from_url(database_url)
    try:
        assert repository.get(first.experiment_id).content_hashes == first.content_hashes
        assert set(repository.execution_ids(first.experiment_id)) == {first.execution_id, second.execution_id}
        assert repository.get(first.experiment_id).deterministic_payload["metadata"]["predictor"]["model_type"] == "sklearn.linear_model.LogisticRegression"
    finally:
        repository.dispose()
