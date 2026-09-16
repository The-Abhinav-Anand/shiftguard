from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen
import zipfile

from shiftguard.datasets.adult import acquire_adult_train_only
from shiftguard.datasets.bank import clean_bank_rows, write_clean_csv


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read_or_download(cache: Path, source_url: str) -> tuple[bytes, str]:
    if cache.is_file():
        return cache.read_bytes(), "verified-local-cache"
    with urlopen(source_url, timeout=60) as response:
        return response.read(), "official-download"


def acquire_bank(
    source_manifest: Path,
    cache: Path,
    raw_output: Path,
    clean_output: Path,
    run_manifest_output: Path,
) -> dict[str, object]:
    contract = json.loads(source_manifest.read_text(encoding="utf-8"))
    archive, retrieval = _read_or_download(cache, contract["source_url"])
    if sha256(archive) != contract["archive_sha256"]:
        raise ValueError("Bank archive SHA-256 does not match the frozen source contract")
    raw_output.parent.mkdir(parents=True, exist_ok=True)
    raw_output.write_bytes(archive)
    with zipfile.ZipFile(io.BytesIO(archive)) as outer:
        nested = outer.read("bank-additional.zip")
    with zipfile.ZipFile(io.BytesIO(nested)) as inner:
        raw_csv = inner.read(contract["raw_member"])
    if sha256(raw_csv) != contract["raw_member_sha256"]:
        raise ValueError("Bank CSV SHA-256 does not match the frozen source contract")
    raw_rows = csv.DictReader(io.StringIO(raw_csv.decode("utf-8")), delimiter=";")
    clean_hash = write_clean_csv(clean_bank_rows(raw_rows), clean_output)
    manifest = {
        **contract,
        "retrieval": retrieval,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "raw_archive_path": str(raw_output),
        "clean_sha256": clean_hash,
        "rows": 41188,
        "predictors": 20,
        "target": "y",
        "cleaning": "stable exact-feature projection; preserves pdays=999, poutcome=nonexistent, and categorical unknown",
    }
    run_manifest_output.parent.mkdir(parents=True, exist_ok=True)
    run_manifest_output.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Acquire, verify, and clean a frozen dataset.")
    parser.add_argument("--dataset", choices=("bank", "adult"), required=True)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--cache", type=Path, default=None)
    parser.add_argument("--raw-output", type=Path, default=None)
    parser.add_argument("--clean-output", type=Path, default=None)
    parser.add_argument("--run-manifest-output", type=Path, default=None)
    args = parser.parse_args()

    if args.dataset == "bank":
        manifest = args.manifest or Path("data/manifests/bank.json")
        cache = args.cache or Path("../.tools/input-cache/bank-marketing.zip")
        raw_output = args.raw_output or Path("data/raw/bank-marketing.zip")
        clean_output = args.clean_output or Path("var/datasets/bank.csv")
        run_manifest_output = args.run_manifest_output or Path("var/datasets/bank.manifest.json")
        result = acquire_bank(manifest, cache, raw_output, clean_output, run_manifest_output)
    else:
        manifest = args.manifest or Path("data/manifests/adult.json")
        cache = args.cache or Path("../.tools/input-cache/adult.data")
        raw_output = args.raw_output or Path("data/raw/adult.data")
        clean_output = args.clean_output or Path("var/datasets/adult.csv")
        run_manifest_output = args.run_manifest_output or Path("var/datasets/adult.manifest.json")
        result = acquire_adult_train_only(manifest, raw_output, clean_output, run_manifest_output, cache)

    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
