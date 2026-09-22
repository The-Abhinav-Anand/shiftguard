from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


BANK_FEATURES = (
    "age", "job", "marital", "education", "default", "housing", "loan", "pdays", "previous", "poutcome",
)
TARGET_COLUMN = "y"
CLEAN_FIELDNAMES = ("row_id", *BANK_FEATURES, TARGET_COLUMN)
FROZEN_BANK_SOURCE = {
    "dataset_id": "uci-bank-marketing-222",
    "source_url": "https://archive.ics.uci.edu/static/public/222/bank+marketing.zip",
    "source_version": "bank-additional-full",
    "license": "CC BY 4.0",
    "citation": "Moro, Rita, Cortez (2014), DOI:10.24432/C5K306",
    "archive_sha256": "e0bf5f5de5b846e2f18e9d90606637267d46dfa260e0f17bb12e605db5efbeb4",
    "raw_member": "bank-additional/bank-additional-full.csv",
    "raw_member_sha256": "74adfc578bf77a7ff4bb1ba4a9f8709d9e3c6907342959c2c8416847e0afb4d8",
}


FROZEN_CLEAN_DIGEST = "0e685060ca6338f712c792ca0bb4e9366fb23808b96ac81886b06eab536bc329"
FROZEN_ROW_COUNT = 41188


@dataclass(frozen=True)
class BankDataset:
    rows: list[dict[str, str | int]]
    raw_hash: str
    clean_hash: str

    @classmethod
    def from_clean_csv(
        cls,
        path: Path,
        manifest: dict[str, object],
        *,
        allow_synthetic: bool = False,
    ) -> BankDataset:
        for key, expected in FROZEN_BANK_SOURCE.items():
            if manifest.get(key) != expected:
                raise ValueError(f"Bank manifest does not match the frozen source identity: {key}")
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if manifest.get("clean_sha256") != actual_hash:
            raise ValueError("Bank clean SHA-256 does not match the run manifest")
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != CLEAN_FIELDNAMES:
                raise ValueError("Bank clean CSV schema must exactly match the frozen feature contract")
            rows = [dict(row) for row in reader]
        normalized = []
        seen_ids: set[int] = set()
        for row in rows:
            if set(row) != set(CLEAN_FIELDNAMES) or None in row:
                raise ValueError("Bank clean CSV contains an unexpected field")
            if row[TARGET_COLUMN] not in {"0", "1"}:
                raise ValueError("Bank clean CSV labels must be binary 0 or 1")
            try:
                row_id = int(row["row_id"])
                for feature in ("age", "pdays", "previous"):
                    if row[feature] not in (None, ""):
                        float(row[feature])
            except (TypeError, ValueError) as error:
                raise ValueError("Bank clean CSV numeric fields are invalid") from error
            if row_id in seen_ids:
                raise ValueError("Bank clean CSV row IDs must be unique")
            seen_ids.add(row_id)
            normalized.append({**row, "row_id": row_id, "y": int(row["y"])})
        if manifest.get("rows") != len(normalized):
            raise ValueError("Bank clean CSV row count does not match the run manifest")
        if hash_clean_rows(normalized) != actual_hash:
            raise ValueError("Bank clean CSV is not canonical UTF-8 with LF newlines")

        if not allow_synthetic:
            if "synthetic" in manifest or "allow_synthetic" in manifest:
                raise ValueError("Bank production clean CSV manifest cannot contain synthetic opt-out flags")
            if actual_hash != FROZEN_CLEAN_DIGEST:
                raise ValueError(f"Bank clean CSV digest {actual_hash} does not match frozen canonical digest {FROZEN_CLEAN_DIGEST}")
            if manifest.get("clean_sha256") != FROZEN_CLEAN_DIGEST:
                raise ValueError("Bank manifest clean_sha256 does not match frozen canonical digest")
            if len(normalized) != FROZEN_ROW_COUNT:
                raise ValueError(f"Bank clean CSV row count {len(normalized)} does not match frozen canonical count {FROZEN_ROW_COUNT}")
            if manifest.get("rows") != FROZEN_ROW_COUNT:
                raise ValueError("Bank manifest rows does not match frozen canonical count")

        return cls(normalized, raw_hash=str(manifest["raw_member_sha256"]), clean_hash=actual_hash)

    @classmethod
    def from_synthetic_csv(cls, path: Path, manifest: dict[str, object]) -> BankDataset:
        return cls.from_clean_csv(path, manifest, allow_synthetic=True)


def clean_bank_rows(raw_rows: Iterable[dict[str, str]]) -> list[dict[str, str | int]]:
    cleaned = []
    for row_id, raw in enumerate(raw_rows, start=1):
        if raw.get(TARGET_COLUMN) not in {"yes", "no"}:
            raise ValueError("Bank target must be yes or no")
        if any(feature not in raw for feature in BANK_FEATURES):
            raise ValueError("Bank source row is missing a required feature")
        cleaned.append({"row_id": row_id, **{feature: raw[feature] for feature in BANK_FEATURES}, "y": int(raw[TARGET_COLUMN] == "yes")})
    return cleaned


def canonical_clean_csv(rows: Iterable[dict[str, str | int]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CLEAN_FIELDNAMES, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def hash_clean_rows(rows: Iterable[dict[str, str | int]]) -> str:
    return hashlib.sha256(canonical_clean_csv(rows)).hexdigest()


def write_clean_csv(rows: list[dict[str, str | int]], path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = canonical_clean_csv(rows)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()
