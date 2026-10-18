"""Build a label-blind Adult source manifest from local files (no network, no labels).

Usage: adult_build_source_manifest.py --data PATH [--test PATH] --release STR --out PATH

Refuses to write under the repository's ``docs/`` tree and refuses to overwrite an existing
file. Prints only counts and the manifest digest, never rows.

Exposure note: a run with ``--test`` reads the adult.test bytes (features are parsed, the label
slot is never read) before the protocol lock. That is an exposure event to record, not
custodian evidence; the manifest it writes is author-built and not custodian-attested.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shiftguard.adult_adapter.features import AdultAdapterError  # noqa: E402
from shiftguard.adult_adapter.source_manifest import (  # noqa: E402
    build_source_manifest,
    manifest_text,
    verify_against_bytes,
)


def _refuse_docs(out: Path) -> None:
    resolved = out.resolve()
    docs = (ROOT / "docs").resolve()
    if resolved == docs or docs in resolved.parents:
        raise AdultAdapterError("OUTPUT_UNDER_DOCS", "out")


def _write_exclusive(path: Path, text: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(path, flags, 0o644)
    except FileExistsError:
        raise AdultAdapterError("OUTPUT_EXISTS", "out") from None
    with os.fdopen(fd, "wb") as handle:
        handle.write(text.encode("ascii"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--test", type=Path)
    parser.add_argument("--release", required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        _refuse_docs(args.out)
        if args.out.exists():
            raise AdultAdapterError("OUTPUT_EXISTS", "out")
        train = args.data.read_bytes()
        test = args.test.read_bytes() if args.test is not None else None
        doc = build_source_manifest(train, test, args.release)
        verify_against_bytes(doc, train, test)  # pins the frozen training file for release uci-adult-2
        _write_exclusive(args.out, manifest_text(doc))
    except AdultAdapterError as exc:
        print(f"error: {exc.code}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: IO {type(exc).__name__}", file=sys.stderr)
        return 2
    train_file = doc["train_file"]
    print(f"status={doc['status']}")
    print(f"train_physical_lines={train_file['physical_line_count']} train_records={train_file['record_line_count']}")
    print(f"train_duplicate_groups={doc['duplicates']['train']['duplicate_group_count']}")
    if doc["test_file"] is not None:
        print(f"test_records={doc['test_file']['record_line_count']} overlap_groups={doc['overlap']['group_count']}")
    print(f"manifest_sha256={doc['manifest_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
