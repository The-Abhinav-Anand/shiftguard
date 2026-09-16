#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from shiftguard.datasets.bank import BankDataset
from shiftguard.experiments.config import StressConfig, load_run_config
from shiftguard.experiments.stress_runner import run_stress_engine
from shiftguard.settings import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed demo stress results for SHIFTGUARD")
    parser.add_argument("--config", type=Path, default=Path("configs/bank-stress.yaml"), help="Path to stress config YAML")
    parser.add_argument("--db-url", type=str, default=None, help="Database URL")
    args = parser.parse_args()

    run_config = load_run_config(args.config)
    if not isinstance(run_config, StressConfig):
        raise ValueError(f"Expected StressConfig, got {type(run_config).__name__}")

    manifest = json.loads(run_config.dataset_manifest.read_text(encoding="utf-8"))
    dataset = BankDataset.from_clean_csv(run_config.dataset_csv, manifest)
    database_url = args.db_url or Settings().db_url

    result = run_stress_engine(dataset, run_config, database_url)
    print(f"Successfully seeded demo results: experiment_id={result.experiment_id}, conditions={len(result.conditions)}")


if __name__ == "__main__":
    main()
