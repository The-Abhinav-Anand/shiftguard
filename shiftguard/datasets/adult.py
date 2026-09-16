from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.request import Request, urlopen

import numpy as np


RAW_ADULT_COLUMNS = (
    "age",
    "workclass",
    "fnlwgt",
    "education",
    "education-num",
    "marital-status",
    "occupation",
    "relationship",
    "race",
    "sex",
    "capital-gain",
    "capital-loss",
    "hours-per-week",
    "native-country",
    "income",
)

# Per blueprint: drop redundant 'education', retain 'education-num'
ADULT_PREDICTORS = (
    "age",
    "workclass",
    "fnlwgt",
    "education-num",
    "marital-status",
    "occupation",
    "relationship",
    "race",
    "sex",
    "capital-gain",
    "capital-loss",
    "hours-per-week",
    "native-country",
)

ADULT_NUMERIC_FEATURES = (
    "age",
    "fnlwgt",
    "education-num",
    "capital-gain",
    "capital-loss",
    "hours-per-week",
)

ADULT_CATEGORICAL_FEATURES = tuple(f for f in ADULT_PREDICTORS if f not in ADULT_NUMERIC_FEATURES)

CLEAN_ADULT_FIELDNAMES = ("row_id", *ADULT_PREDICTORS, "income")

FROZEN_ADULT_SOURCE = {
    "dataset_id": "uci-adult-2",
    "source_url": "https://archive.ics.uci.edu/ml/machine-learning-databases/adult/adult.data",
    "source_version": "adult.data",
    "raw_sha256": "5b00264637dbfec36bdeaab5676b0b309ff9eb788d63554ca0a249491c86603d",
    "license": "CC BY 4.0",
    "citation": "Becker and Kohavi (1996), DOI:10.24432/C5XW20",
    "raw_records": 32561,
}

ADULT_ROLE_FRACTIONS = {
    "train": 0.6875,
    "source_cal": 0.1875,
    "target_pool": 0.1250,
}


def normalize_income_label(raw: str) -> int:
    """Normalize income label, stripping any trailing period (e.g. from test fixtures)."""
    cleaned = raw.strip().rstrip(".")
    if cleaned == "<=50K":
        return 0
    if cleaned == ">50K":
        return 1
    raise ValueError(f"Unknown income label: {raw!r}")


def clean_adult_rows(raw_lines: Iterable[str]) -> list[dict[str, str | int | None]]:
    """Deterministically parse and clean raw adult.data lines."""
    rows = []
    row_id = 1
    for line in raw_lines:
        line_str = line.strip()
        if not line_str:
            continue
        parts = [p.strip() for p in line_str.split(",")]
        if len(parts) != len(RAW_ADULT_COLUMNS):
            raise ValueError(f"Expected {len(RAW_ADULT_COLUMNS)} fields, got {len(parts)} in line: {line_str}")

        raw_dict = dict(zip(RAW_ADULT_COLUMNS, parts, strict=True))

        cleaned_row: dict[str, str | int | None] = {"row_id": row_id}
        for feature in ADULT_PREDICTORS:
            val = raw_dict[feature]
            if val == "?":
                cleaned_row[feature] = None
            elif feature in ADULT_NUMERIC_FEATURES:
                cleaned_row[feature] = int(val) if val.isdigit() else float(val)
            else:
                cleaned_row[feature] = val

        cleaned_row["income"] = normalize_income_label(raw_dict["income"])
        rows.append(cleaned_row)
        row_id += 1

    return rows


def write_clean_adult_csv(rows: list[dict[str, str | int | None]], path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CLEAN_ADULT_FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            formatted = {}
            for k in CLEAN_ADULT_FIELDNAMES:
                v = row[k]
                formatted[k] = "" if v is None else str(v)
            writer.writerow(formatted)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_adult_role_splits(rows: list[dict[str, object]], seed: int) -> dict[str, tuple[int, ...]]:
    """Partition adult.data into train (68.75%), source_cal (18.75%), and target_pool (12.50%)."""
    rng = np.random.default_rng(seed)
    row_ids = np.array([int(r["row_id"]) for r in rows])
    perm = rng.permutation(row_ids)
    n = len(perm)

    n_train = int(round(n * ADULT_ROLE_FRACTIONS["train"]))
    n_source = int(round(n * ADULT_ROLE_FRACTIONS["source_cal"]))

    train_ids = tuple(int(x) for x in sorted(perm[:n_train]))
    source_ids = tuple(int(x) for x in sorted(perm[n_train:n_train + n_source]))
    pool_ids = tuple(int(x) for x in sorted(perm[n_train + n_source:]))

    # Invariance check: disjoint and exhaustive
    s_train, s_source, s_pool = set(train_ids), set(source_ids), set(pool_ids)
    assert len(s_train & s_source) == 0, "train and source_cal overlap"
    assert len(s_train & s_pool) == 0, "train and target_pool overlap"
    assert len(s_source & s_pool) == 0, "source_cal and target_pool overlap"
    assert len(s_train | s_source | s_pool) == n, "roles do not cover all records"

    return {
        "train": train_ids,
        "source_cal": source_ids,
        "target_pool": pool_ids,
    }


def acquire_adult_train_only(
    source_manifest: Path,
    raw_output: Path,
    clean_output: Path,
    run_manifest_output: Path,
    cache: Path | None = None,
) -> dict[str, object]:
    """Acquire ONLY the official training file adult.data. Rejects any request for adult.test."""
    manifest_data = json.loads(source_manifest.read_text(encoding="utf-8"))
    source_url = manifest_data["source_url"]

    # Security check: must not request adult.test or combined archive
    if "adult.test" in source_url:
        raise ValueError("Confirmatory test file adult.test acquisition is forbidden in Gate 3")
    if source_url.endswith(".zip"):
        raise ValueError("Combined archive acquisition is forbidden; must acquire adult.data directly")

    if cache is not None and cache.is_file():
        raw_bytes = cache.read_bytes()
        retrieval = "verified-local-cache"
    else:
        req = Request(source_url, headers={"User-Agent": "SHIFTGUARD/1.0 (UCI Adult Acquisition)"})
        with urlopen(req, timeout=60) as resp:
            raw_bytes = resp.read()
        retrieval = "official-download"

    actual_hash = hashlib.sha256(raw_bytes).hexdigest()
    if actual_hash != manifest_data["raw_sha256"]:
        raise ValueError(f"adult.data SHA-256 mismatch: expected {manifest_data['raw_sha256']}, got {actual_hash}")

    raw_output.parent.mkdir(parents=True, exist_ok=True)
    raw_output.write_bytes(raw_bytes)

    lines = raw_bytes.decode("utf-8", errors="replace").splitlines()
    cleaned_rows = clean_adult_rows(lines)
    if len(cleaned_rows) != manifest_data["raw_records"]:
        raise ValueError(f"Expected {manifest_data['raw_records']} records, got {len(cleaned_rows)}")

    clean_sha256 = write_clean_adult_csv(cleaned_rows, clean_output)

    run_manifest = {
        **manifest_data,
        "retrieval": retrieval,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "raw_data_path": str(raw_output),
        "clean_data_path": str(clean_output),
        "clean_sha256": clean_sha256,
        "records_count": len(cleaned_rows),
        "role_allocation": ADULT_ROLE_FRACTIONS,
        "predictors": list(ADULT_PREDICTORS),
        "target": "income",
        "confirmatory_test_sealed": True,
    }

    run_manifest_output.parent.mkdir(parents=True, exist_ok=True)
    run_manifest_output.write_text(json.dumps(run_manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return run_manifest


def execute_adult_confirmatory() -> None:
    """Execution guard ensuring Adult confirmatory execution remains sealed until Gate 8 protocol lock."""
    raise RuntimeError("Adult confirmatory execution is sealed until Gate 8 protocol lock.")
