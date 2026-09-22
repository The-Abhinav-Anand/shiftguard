from __future__ import annotations

import hashlib
import json
import sys
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from scripts.seed_demo_results import main as seed_main
from shiftguard.cli import app
from shiftguard.datasets.bank import BankDataset, FROZEN_BANK_SOURCE, write_clean_csv

_orig_from_clean_csv = BankDataset.from_clean_csv


@pytest.fixture(autouse=True)
def _patch_cli_synthetic_dataset(monkeypatch):
    monkeypatch.setattr("shiftguard.cli.BankDataset.from_clean_csv", lambda p, m, **kw: _orig_from_clean_csv(p, m, allow_synthetic=True))
    monkeypatch.setattr("scripts.seed_demo_results.BankDataset.from_clean_csv", lambda p, m, **kw: _orig_from_clean_csv(p, m, allow_synthetic=True))


def _fixture_manifest(dataset_csv, rows: int) -> dict[str, object]:
    return {
        **FROZEN_BANK_SOURCE,
        "clean_sha256": hashlib.sha256(dataset_csv.read_bytes()).hexdigest(),
        "rows": rows,
    }


def _create_test_dataset(tmp_path, rows_count: int = 600):
    rows = []
    for row_id in range(1, rows_count + 1):
        rows.append({
            "row_id": row_id,
            "age": str(20 + row_id % 40),
            "job": "admin." if row_id % 2 else "technician",
            "marital": "single" if row_id % 3 else "married",
            "education": "secondary",
            "default": "no",
            "housing": "yes",
            "loan": "no",
            "pdays": "999" if row_id % 4 else "5",
            "previous": str(row_id % 3),
            "poutcome": "nonexistent" if row_id % 4 else "success",
            "y": row_id % 2,
        })
    dataset_csv = tmp_path / "bank.csv"
    write_clean_csv(rows, dataset_csv)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(_fixture_manifest(dataset_csv, len(rows))), encoding="utf-8")
    return dataset_csv, manifest


def test_cli_reports_bootstrap_status(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'shiftguard.db'}"
    result = CliRunner().invoke(app, ["--db-url", database_url, "status"])

    assert result.exit_code == 0
    assert "Gate 0 bootstrap ready" in result.stdout


def test_cli_runs_gate1_config(tmp_path) -> None:
    dataset_csv, manifest = _create_test_dataset(tmp_path, rows_count=100)
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps({
            "master_seed": 31001,
            "dataset_csv": str(dataset_csv),
            "dataset_manifest": str(manifest),
            "artifact_root": str(tmp_path / "artifacts"),
        }),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["--db-url", f"sqlite:///{tmp_path / 'gate1.db'}", "run", "--config", str(config)])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "experiment_id" in data
    assert "execution_id" in data
    assert "metrics" in data


def test_cli_runs_outage_config(tmp_path) -> None:
    """Verify CLI dispatch and JSON output for OutageConfig (Gate 2)."""
    dataset_csv, manifest = _create_test_dataset(tmp_path, rows_count=600)
    config = tmp_path / "outage_config.json"
    config.write_text(
        json.dumps({
            "master_seed": 31001,
            "run_type": "outage_recovery",
            "dataset_csv": str(dataset_csv),
            "dataset_manifest": str(manifest),
            "artifact_root": str(tmp_path / "artifacts_outage"),
        }),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["--db-url", f"sqlite:///{tmp_path / 'outage.db'}", "run", "--config", str(config)])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "experiment_id" in data
    assert "execution_id" in data
    assert "conditions" in data
    assert "comparisons" in data
    assert "content_hashes" in data


def test_cli_runs_stress_config(tmp_path) -> None:
    """Verify CLI dispatch and JSON output for StressConfig (Gate 3)."""
    dataset_csv, manifest = _create_test_dataset(tmp_path, rows_count=800)
    config = tmp_path / "stress_config.json"
    config.write_text(
        json.dumps({
            "master_seed": 31001,
            "run_type": "stress_engine",
            "protocol_id": "sg-protocol-1.0-draft-gate3",
            "evaluation_tier": "development",
            "predictors": ["logistic_regression"],
            "budgets": [0, 50],
            "mcar_rates": [0.0],
            "history_row_probability": 0.50,
            "calibration_methods": ["raw"],
            "cost_grid": [[1.0, 1.0]],
            "dataset_csv": str(dataset_csv),
            "dataset_manifest": str(manifest),
            "artifact_root": str(tmp_path / "artifacts_stress"),
        }),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["--db-url", f"sqlite:///{tmp_path / 'stress.db'}", "run", "--config", str(config)])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "experiment_id" in data
    assert "execution_id" in data
    assert "condition_count" in data
    assert "payload_keys" in data
    assert "content_hashes" in data


def test_cli_rejects_unknown_keys_and_confirmatory_config(tmp_path) -> None:
    """CLI rejects invalid configurations and forbidden adult_confirmatory run_type."""
    # Unknown key
    config_unknown = tmp_path / "unknown_config.json"
    config_unknown.write_text(
        json.dumps({"master_seed": 31001, "unrecognized_key_xyz": 123}),
        encoding="utf-8",
    )
    res_unknown = CliRunner().invoke(app, ["run", "--config", str(config_unknown)])
    assert res_unknown.exit_code != 0

    # Forbidden adult confirmatory
    config_confirmatory = tmp_path / "confirmatory.json"
    config_confirmatory.write_text(
        json.dumps({"run_type": "adult_confirmatory"}),
        encoding="utf-8",
    )
    res_conf = CliRunner().invoke(app, ["run", "--config", str(config_confirmatory)])
    assert res_conf.exit_code != 0
    assert "sealed" in str(res_conf.exception)


def test_cli_rejects_tampered_clean_csv_before_partition(tmp_path) -> None:
    rows = [{"row_id": 1, "age": "30", "job": "admin.", "marital": "single", "education": "secondary", "default": "no", "housing": "yes", "loan": "no", "pdays": "999", "previous": "0", "poutcome": "nonexistent", "y": 0}]
    dataset_csv = tmp_path / "bank.csv"
    write_clean_csv(rows, dataset_csv)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(_fixture_manifest(dataset_csv, len(rows))), encoding="utf-8")
    dataset_csv.write_bytes(dataset_csv.read_bytes().replace(b"admin.", b"tamper"))
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"master_seed": 31001, "dataset_csv": str(dataset_csv), "dataset_manifest": str(manifest), "artifact_root": str(tmp_path / "artifacts")}), encoding="utf-8")

    result = CliRunner().invoke(app, ["--db-url", f"sqlite:///{tmp_path / 'gate1.db'}", "run", "--config", str(config)])

    assert result.exit_code != 0
    assert "clean SHA-256" in str(result.exception)


def test_seed_demo_results_entrypoint_and_rejection(tmp_path, capsys) -> None:
    """Verify scripts/seed_demo_results.py works with StressConfig and rejects non-StressConfig."""
    dataset_csv, manifest = _create_test_dataset(tmp_path, rows_count=800)
    stress_cfg_path = tmp_path / "demo_stress.json"
    stress_cfg_path.write_text(
        json.dumps({
            "master_seed": 31001,
            "run_type": "stress_engine",
            "protocol_id": "sg-protocol-1.0-draft-gate3",
            "evaluation_tier": "development",
            "predictors": ["logistic_regression"],
            "budgets": [0, 50],
            "mcar_rates": [0.0],
            "history_row_probability": 0.50,
            "calibration_methods": ["raw"],
            "cost_grid": [[1.0, 1.0]],
            "dataset_csv": str(dataset_csv),
            "dataset_manifest": str(manifest),
            "artifact_root": str(tmp_path / "artifacts_seed"),
        }),
        encoding="utf-8",
    )
    db_url = f"sqlite:///{tmp_path / 'seed_demo.db'}"

    # Valid run
    with patch.object(sys, "argv", ["seed_demo_results.py", "--config", str(stress_cfg_path), "--db-url", db_url]):
        seed_main()
    captured = capsys.readouterr()
    assert "Successfully seeded demo results" in captured.out

    # Rejection of non-StressConfig
    baseline_cfg_path = tmp_path / "demo_baseline.json"
    baseline_cfg_path.write_text(
        json.dumps({
            "master_seed": 31001,
            "dataset_csv": str(dataset_csv),
            "dataset_manifest": str(manifest),
            "artifact_root": str(tmp_path / "artifacts_baseline"),
        }),
        encoding="utf-8",
    )
    with patch.object(sys, "argv", ["seed_demo_results.py", "--config", str(baseline_cfg_path), "--db-url", db_url]):
        with pytest.raises(ValueError, match="Expected StressConfig"):
            seed_main()
