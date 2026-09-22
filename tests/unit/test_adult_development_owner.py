from __future__ import annotations

import hashlib
import json
from pathlib import Path
import pytest

from shiftguard.datasets.adult import (
    ADULT_PREDICTORS,
    ADULT_ROLE_FRACTIONS,
    FROZEN_ADULT_SOURCE,
    acquire_adult_train_only,
    clean_adult_rows,
    execute_adult_confirmatory,
    make_adult_role_splits,
    normalize_income_label,
    write_clean_adult_csv,
)
from shiftguard.experiments.config import load_run_config
from shiftguard.protocol.acquisition import LabelBlindTargetProvider


def test_adult_confirmatory_config_sealed() -> None:
    config_path = Path("configs/adult-confirmatory.yaml")
    assert config_path.is_file()

    with pytest.raises(RuntimeError, match="Adult confirmatory execution is sealed until Gate 8 protocol lock"):
        load_run_config(config_path)

    with pytest.raises(RuntimeError, match="Adult confirmatory execution is sealed until Gate 8 protocol lock"):
        execute_adult_confirmatory()


def test_adult_label_normalization_handles_trailing_periods() -> None:
    # Synthetic test fixture simulating future adult.test labels without downloading the official test file
    assert normalize_income_label("<=50K") == 0
    assert normalize_income_label("<=50K.") == 0
    assert normalize_income_label(" >50K") == 1
    assert normalize_income_label(" >50K.") == 1

    with pytest.raises(ValueError):
        normalize_income_label("invalid_label")


def test_adult_clean_rows_and_natural_missing() -> None:
    # Sample synthetic raw line
    raw_line_1 = "39, State-gov, 77516, Bachelors, 13, Never-married, Adm-clerical, Not-in-family, White, Male, 2174, 0, 40, United-States, <=50K"
    raw_line_with_question = "50, ?, 12345, HS-grad, 9, Married-civ-spouse, ?, Husband, White, Male, 0, 0, 40, ?, >50K"

    cleaned = clean_adult_rows([raw_line_1, raw_line_with_question])
    assert len(cleaned) == 2

    # Verify line 1
    assert cleaned[0]["row_id"] == 1
    assert cleaned[0]["age"] == 39
    assert cleaned[0]["workclass"] == "State-gov"
    assert cleaned[0]["education-num"] == 13
    assert "education" not in cleaned[0]  # Redundant column dropped
    assert cleaned[0]["income"] == 0

    # Verify line 2 with natural missing '?'
    assert cleaned[1]["row_id"] == 2
    assert cleaned[1]["workclass"] is None
    assert cleaned[1]["occupation"] is None
    assert cleaned[1]["native-country"] is None
    assert cleaned[1]["income"] == 1


def test_adult_role_splits_disjoint_and_proportions() -> None:
    n = 32561
    dummy_rows = [{"row_id": i + 1, "income": i % 2} for i in range(n)]
    roles = make_adult_role_splits(dummy_rows, seed=31001)

    train = set(roles["train"])
    source = set(roles["source_cal"])
    pool = set(roles["target_pool"])

    # Disjointness
    assert len(train & source) == 0
    assert len(train & pool) == 0
    assert len(source & pool) == 0
    assert len(train | source | pool) == n

    # Proportions: 68.75% / 18.75% / 12.50%
    assert len(train) == 22386
    assert len(source) == 6105
    assert len(pool) == 4070


def test_adult_label_blind_acquisition_order() -> None:
    dummy_pool = tuple({"row_id": i + 1, "age": 30, "income": i % 2} for i in range(500))
    provider1 = LabelBlindTargetProvider(dummy_pool, seed=31501, target_column="income")
    provider2 = LabelBlindTargetProvider(dummy_pool, seed=31501, target_column="income")

    assert provider1.order == provider2.order

    # Nested prefixes
    prefix_25 = provider1.reveal_prefix(25)
    prefix_50 = provider1.reveal_prefix(50)

    assert prefix_50.record_ids[:25] == prefix_25.record_ids
    assert len(prefix_25.labels) == 25
    assert len(prefix_50.labels) == 50


def test_adult_acquisition_rejects_test_file(tmp_path: Path) -> None:
    bad_manifest = tmp_path / "bad.json"
    bad_manifest.write_text(json.dumps({
        "dataset_id": "uci-adult-2",
        "source_version": "adult.data",
        "source_url": "https://archive.ics.uci.edu/ml/machine-learning-databases/adult/adult.test",
        "raw_sha256": "5b00264637dbfec36bdeaab5676b0b309ff9eb788d63554ca0a249491c86603d",
        "raw_records": 32561,
    }))

    raw_out = tmp_path / "raw"
    clean_out = tmp_path / "clean"
    run_out = tmp_path / "run.json"

    with pytest.raises(ValueError, match="Confirmatory test file adult.test acquisition is forbidden"):
        acquire_adult_train_only(bad_manifest, raw_out, clean_out, run_out)
    assert not raw_out.exists()
    assert not clean_out.exists()
    assert not run_out.exists()


def test_adult_acquisition_with_local_cache_authoritative_seam(tmp_path: Path) -> None:
    manifest_path = Path("data/manifests/adult.json")
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Create dummy raw data matching manifest record count
    raw_lines = [
        "39, State-gov, 77516, Bachelors, 13, Never-married, Adm-clerical, Not-in-family, White, Male, 2174, 0, 40, United-States, <=50K"
    ] * manifest_data["raw_records"]
    raw_content = "\n".join(raw_lines).encode("utf-8")
    actual_hash = hashlib.sha256(raw_content).hexdigest()

    authoritative_fixture = {
        **manifest_data,
        "raw_sha256": actual_hash,
    }

    test_manifest = tmp_path / "test_manifest.json"
    test_manifest.write_text(json.dumps(authoritative_fixture))

    cache_file = tmp_path / "cache.data"
    cache_file.write_bytes(raw_content)

    run_manifest = acquire_adult_train_only(
        source_manifest=test_manifest,
        raw_output=tmp_path / "data/raw/adult.data",
        clean_output=tmp_path / "var/datasets/adult.csv",
        run_manifest_output=tmp_path / "var/datasets/adult.manifest.json",
        cache=cache_file,
        _authoritative_source=authoritative_fixture,
    )

    assert run_manifest["records_count"] == manifest_data["raw_records"]
    assert run_manifest["confirmatory_test_sealed"] is True
    assert Path(run_manifest["clean_data_path"]).is_file()


def test_adult_acquisition_rejects_mutated_manifest_identity(tmp_path: Path) -> None:
    base = dict(FROZEN_ADULT_SOURCE)
    raw_out = tmp_path / "raw"
    clean_out = tmp_path / "clean"
    run_out = tmp_path / "run.json"

    # Mutated dataset_id
    bad_id = tmp_path / "bad_id.json"
    bad_id.write_text(json.dumps({**base, "dataset_id": "substituted"}))
    with pytest.raises(ValueError, match="dataset_id mismatch"):
        acquire_adult_train_only(bad_id, raw_out, clean_out, run_out)
    assert not raw_out.exists()

    # Mutated raw_sha256
    bad_hash = tmp_path / "bad_hash.json"
    bad_hash.write_text(json.dumps({**base, "raw_sha256": "0" * 64}))
    with pytest.raises(ValueError, match="raw_sha256 mismatch"):
        acquire_adult_train_only(bad_hash, raw_out, clean_out, run_out)
    assert not raw_out.exists()

    # Mutated records count
    bad_records = tmp_path / "bad_records.json"
    bad_records.write_text(json.dumps({**base, "raw_records": 100}))
    with pytest.raises(ValueError, match="raw_records mismatch"):
        acquire_adult_train_only(bad_records, raw_out, clean_out, run_out)
    assert not raw_out.exists()

    # Unapproved source URL
    bad_url = tmp_path / "bad_url.json"
    bad_url.write_text(json.dumps({**base, "source_url": "https://invalid.example/adult.data"}))
    with pytest.raises(ValueError, match="Unapproved Adult training URL"):
        acquire_adult_train_only(bad_url, raw_out, clean_out, run_out)
    assert not raw_out.exists()


def test_adult_acquisition_rejects_forbidden_cache_path(tmp_path: Path) -> None:
    manifest_path = Path("data/manifests/adult.json")
    raw_out = tmp_path / "raw"
    clean_out = tmp_path / "clean"
    run_out = tmp_path / "run.json"

    forbidden_cache = tmp_path / "adult.test"
    forbidden_cache.write_bytes(b"forbidden")
    with pytest.raises(ValueError, match="Confirmatory test file adult.test cache is strictly forbidden"):
        acquire_adult_train_only(manifest_path, raw_out, clean_out, run_out, cache=forbidden_cache)
    assert not raw_out.exists()

    zip_cache = tmp_path / "archive.zip"
    zip_cache.write_bytes(b"PK...")
    with pytest.raises(ValueError, match="Combined archive cache is forbidden"):
        acquire_adult_train_only(manifest_path, raw_out, clean_out, run_out, cache=zip_cache)
    assert not raw_out.exists()


def test_adult_acquisition_rejects_corrupt_cache_bytes(tmp_path: Path) -> None:
    manifest_path = Path("data/manifests/adult.json")
    raw_out = tmp_path / "raw"
    clean_out = tmp_path / "clean"
    run_out = tmp_path / "run.json"

    bad_bytes_cache = tmp_path / "corrupt.data"
    bad_bytes_cache.write_bytes(b"not valid adult data")
    with pytest.raises(ValueError, match="adult.data SHA-256 mismatch"):
        acquire_adult_train_only(manifest_path, raw_out, clean_out, run_out, cache=bad_bytes_cache)
    assert not raw_out.exists()
    assert not clean_out.exists()
    assert not run_out.exists()
