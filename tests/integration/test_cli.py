from __future__ import annotations

import json

from typer.testing import CliRunner

from shiftguard.cli import app
from shiftguard.datasets.bank import FROZEN_BANK_SOURCE, write_clean_csv


def _fixture_manifest(dataset_csv, rows: int) -> dict[str, object]:
    return {**FROZEN_BANK_SOURCE, "clean_sha256": __import__("hashlib").sha256(dataset_csv.read_bytes()).hexdigest(), "rows": rows}


def test_cli_reports_bootstrap_status(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'shiftguard.db'}"
    result = CliRunner().invoke(app, ["--db-url", database_url, "status"])

    assert result.exit_code == 0
    assert "Gate 0 bootstrap ready" in result.stdout


def test_cli_runs_gate1_config(tmp_path) -> None:
    rows = []
    for row_id in range(1, 101):
        rows.append({"row_id": row_id, "age": str(20 + row_id % 40), "job": "admin." if row_id % 2 else "technician", "marital": "single", "education": "secondary", "default": "no", "housing": "yes", "loan": "no", "pdays": "999", "previous": "0", "poutcome": "nonexistent", "y": row_id % 2})
    dataset_csv = tmp_path / "bank.csv"
    write_clean_csv(rows, dataset_csv)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(_fixture_manifest(dataset_csv, len(rows))), encoding="utf-8")
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"master_seed": 31001, "dataset_csv": str(dataset_csv), "dataset_manifest": str(manifest), "artifact_root": str(tmp_path / "artifacts")}), encoding="utf-8")

    result = CliRunner().invoke(app, ["--db-url", f"sqlite:///{tmp_path / 'gate1.db'}", "run", "--config", str(config)])

    assert result.exit_code == 0
    assert "experiment_id" in result.stdout


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
