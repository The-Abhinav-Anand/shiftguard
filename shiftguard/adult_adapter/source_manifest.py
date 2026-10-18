"""Label-blind source manifest for the official Adult archive files (Gate 9 prerequisite 1 tooling).

Author-built tooling, exercised on fabricated rows. A manifest it produces is not
custodian-attested and is not evidence about any outcome.

How the label stays unread
--------------------------
Files are read as bytes. A line must contain exactly 14 commas (15 fields). The feature
region is then taken as the slice ``line[:line.rindex(b",")]``: the 15th (label) slot is
never sliced out, bound to a name, decoded, stripped, compared or counted. Label bytes
enter the manifest only through (a) whole-file ``byte_size`` and ``sha256`` (file
identity), (b) the field-count check (a label containing a comma is a typed
``FIELD_COUNT`` rejection) and (c) line-terminator detection (the ``\\n`` / trailing
``\\r`` that ends the line). Garbage label bytes, including invalid UTF-8, have no other
effect.

Side channel, deliberately closed: ``<=50K`` and ``>50K`` differ in length by one byte,
so ``byte_size`` minus the summed feature-region lengths would reveal label prevalence.
No feature-region (or per-line) length is ever computed or published; do not add one.

Record construction: ``AdultRecord``/``record_from_raw_fields`` already have no label
slot, so they are reused. The 14 raw feature fields are the raw columns minus ``income``;
the redundant ``education`` column is dropped exactly as the frozen parser's predictor
list does, then ``record_from_raw_fields`` applies its strip / ``?`` -> null rules and
``grouping.group_key`` hashes the tokens. Feature bytes must be ASCII with no control
byte except tab (no bytes below 0x20 other than ``\\t``, no 0x7F).

Line endings: file hashes cover the raw bytes as-is. Lines split on ``\\n``; a trailing
``\\r`` on a ``\\n``-terminated line is removed before parsing (CRLF == LF for parsing);
any other ``\\r`` in the feature region is rejected (``BARE_CR``). ``crlf_lines``,
``lf_only_lines`` and ``unterminated_lines`` (0 or 1: a last line with no newline) are
recorded so a conversion is visible.

Skipped lines (physical number and reason only): ``blank`` (empty or whitespace-only) and
``comment_header`` (physical line 1 of adult.test only, starting with ``|``). Anything else
that is not a 15-field row is an error, never silently skipped. A file with no records
is rejected.

What self-verification cannot detect
------------------------------------
``verify_source_manifest`` checks the digest, a closed schema and internal consistency
only. A forger can fabricate a coherent manifest, recompute ``manifest_sha256`` and pass
it; it also cannot tell that the hashes describe the right archive or that the files were
read untampered. ``verify_against_bytes`` rebuilds from the real bytes and requires exact
equality (and, for release ``uci-adult-2``, pins the frozen training sha256 and record
count), but still proves nothing about the provenance of the bytes themselves.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from shiftguard.adult_adapter.features import (
    ADULT_FEATURE_CONTRACT,
    DEVELOPMENT_SOURCE_FILE,
    AdultAdapterError,
    canonical_digest,
    canonical_json,
    digest_field,
    make_row_id,
    parse_row_id,
    record_from_raw_fields,
)
from shiftguard.adult_adapter.grouping import FEATURE_GROUP_VERSION, group_key
from shiftguard.datasets.adult import FROZEN_ADULT_SOURCE, RAW_ADULT_COLUMNS


MANIFEST_SCHEMA = "adult-source-manifest-v1"
LABEL_POLICY = (
    "label field never decoded, compared or counted; label bytes enter only whole-file "
    "byte_size/sha256, the field-count check and line-terminator detection"
)
CUSTODIAN_STATUS = "author-built, not custodian-attested"
TEST_SOURCE_FILE = "adult.test"
STATUS_TRAIN_ONLY = "train_only"
STATUS_TRAIN_AND_TEST = "train_and_test"
FROZEN_RELEASE = "uci-adult-2"

_COMMAS = len(RAW_ADULT_COLUMNS) - 1  # 14 commas separate 15 fields
_FEATURE_SLOTS = tuple(
    (index, name) for index, name in enumerate(RAW_ADULT_COLUMNS[:-1]) if name in ADULT_FEATURE_CONTRACT.features
)
_FILE_KEYS = (
    "name", "byte_size", "sha256", "physical_line_count", "record_line_count",
    "skipped_lines", "line_endings", "record_group_digest",
)
_ENDING_KEYS = ("crlf_lines", "lf_only_lines", "unterminated_lines", "final_newline")
_DUP_KEYS = ("group_count_total", "duplicate_group_count", "duplicate_row_count", "groups")
_OVERLAP_KEYS = ("group_count", "train_row_count", "test_row_count", "groups")
_BODY_KEYS = (
    "schema", "release", "label_policy", "custodian_status", "status", "tool_versions",
    "train_file", "test_file", "duplicates", "overlap", "test_connected_group_keys",
)
_SKIP_REASONS = ("blank", "comment_header")


def _split_physical_lines(data: bytes) -> list[bytes]:
    lines = data.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()  # file ended with a newline: no extra physical line
    return lines


def _bad_control(feature_bytes: bytes) -> bool:
    return any((b < 0x20 and b != 0x09) or b == 0x7F for b in feature_bytes)


def _scan_file(data: bytes, release: str, source_file: str) -> tuple[dict[str, Any], dict[str, list[int]]]:
    """Return (file section, group key -> sorted line numbers)."""
    if type(data) is not bytes:
        raise AdultAdapterError("FILE_BYTES", source_file)
    lines = _split_physical_lines(data)
    unterminated = 1 if data and not data.endswith(b"\n") else 0
    terminated = len(lines) - unterminated
    skipped: list[dict[str, Any]] = []
    groups: dict[str, list[int]] = {}
    ordered: list[list[Any]] = []
    crlf = 0
    for number, raw in enumerate(lines, start=1):
        line = raw
        if number <= terminated and line.endswith(b"\r"):
            line = line[:-1]
            crlf += 1
        if not line.strip():
            skipped.append({"line": number, "reason": "blank"})
            continue
        if number == 1 and line.startswith(b"|"):
            if source_file != TEST_SOURCE_FILE:
                raise AdultAdapterError("HEADER_IN_TRAIN", f"{source_file}:{number}")
            skipped.append({"line": number, "reason": "comment_header"})
            continue
        if line.count(b",") != _COMMAS:
            raise AdultAdapterError("FIELD_COUNT", f"{source_file}:{number}")
        # Structural label discard: the slice stops at the last comma, so the 15th slot is never read.
        feature_bytes = line[: line.rindex(b",")]
        if b"\r" in feature_bytes:
            raise AdultAdapterError("BARE_CR", f"{source_file}:{number}")
        if _bad_control(feature_bytes):
            raise AdultAdapterError("CONTROL_BYTE", f"{source_file}:{number}")
        try:
            text = feature_bytes.decode("ascii")
        except UnicodeDecodeError:
            raise AdultAdapterError("NON_ASCII_FEATURE", f"{source_file}:{number}") from None
        parts = text.split(",")
        fields = {name: parts[index] for index, name in _FEATURE_SLOTS}
        try:
            record = record_from_raw_fields(make_row_id(release, source_file, number), fields)
        except AdultAdapterError as exc:
            raise AdultAdapterError(exc.code, f"{source_file}:{number}:{exc.detail}") from None
        key = group_key(record)
        groups.setdefault(key, []).append(number)
        ordered.append([number, key])
    if not ordered:
        raise AdultAdapterError("NO_RECORDS", source_file)
    section = {
        "name": source_file,
        "byte_size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "physical_line_count": len(lines),
        "record_line_count": len(ordered),
        "skipped_lines": skipped,
        "line_endings": {
            "crlf_lines": crlf,
            "lf_only_lines": terminated - crlf,
            "unterminated_lines": unterminated,
            "final_newline": unterminated == 0,
        },
        "record_group_digest": canonical_digest(ordered),
    }
    return section, groups


def _duplicates(release: str, source_file: str, groups: dict[str, list[int]]) -> dict[str, Any]:
    dup = {k: v for k, v in groups.items() if len(v) >= 2}
    return {
        "group_count_total": len(groups),
        "duplicate_group_count": len(dup),
        "duplicate_row_count": sum(len(v) for v in dup.values()),
        "groups": [
            {"group_key": k, "row_ids": [make_row_id(release, source_file, n) for n in sorted(dup[k])]}
            for k in sorted(dup)
        ],
    }


def build_source_manifest(train_bytes: bytes, test_bytes: bytes | None, release: str) -> dict[str, Any]:
    """Build the manifest document from raw file bytes (test bytes optional)."""
    make_row_id(release, DEVELOPMENT_SOURCE_FILE, 1)  # validates the release string
    train_section, train_groups = _scan_file(train_bytes, release, DEVELOPMENT_SOURCE_FILE)
    duplicates = {"train": _duplicates(release, DEVELOPMENT_SOURCE_FILE, train_groups)}
    test_section = overlap = connected = None
    status = STATUS_TRAIN_ONLY
    if test_bytes is not None:
        test_section, test_groups = _scan_file(test_bytes, release, TEST_SOURCE_FILE)
        duplicates["test"] = _duplicates(release, TEST_SOURCE_FILE, test_groups)
        shared = sorted(train_groups.keys() & test_groups.keys())
        overlap = {
            "group_count": len(shared),
            "train_row_count": sum(len(train_groups[k]) for k in shared),
            "test_row_count": sum(len(test_groups[k]) for k in shared),
            "groups": [
                {"group_key": k, "train_row_count": len(train_groups[k]), "test_row_count": len(test_groups[k])}
                for k in shared
            ],
        }
        connected = list(shared)
        status = STATUS_TRAIN_AND_TEST
    body = {
        "schema": MANIFEST_SCHEMA,
        "release": release,
        "label_policy": LABEL_POLICY,
        "custodian_status": CUSTODIAN_STATUS,
        "status": status,
        "tool_versions": {
            "feature_group_version": FEATURE_GROUP_VERSION,
            "feature_schema_digest": ADULT_FEATURE_CONTRACT.schema_digest,
        },
        "train_file": train_section,
        "test_file": test_section,
        "duplicates": duplicates,
        "overlap": overlap,
        "test_connected_group_keys": connected,
    }
    return {**body, "manifest_sha256": canonical_digest(body)}


# ---------------------------------------------------------------- verification helpers


def _shape(value: Any, keys: tuple[str, ...], name: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != set(keys):
        raise AdultAdapterError("MANIFEST_SHAPE", name)
    return value


def _count(value: Any, name: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:  # bool and float are rejected here
        raise AdultAdapterError("MANIFEST_SHAPE", name)
    return value


def _array(value: Any, name: str) -> list:
    if type(value) is not list:
        raise AdultAdapterError("MANIFEST_SHAPE", name)
    return value


def _check_file(section: Any, source_file: str) -> set[int]:
    """Validate one file block; return its skipped physical line numbers."""
    section = _shape(section, _FILE_KEYS, source_file)
    if section["name"] != source_file:
        raise AdultAdapterError("MANIFEST_FILE", f"{source_file}.name")
    digest_field(section["sha256"], f"{source_file}.sha256")
    digest_field(section["record_group_digest"], f"{source_file}.record_group_digest")
    _count(section["byte_size"], f"{source_file}.byte_size")
    physical = _count(section["physical_line_count"], f"{source_file}.physical_line_count")
    records = _count(section["record_line_count"], f"{source_file}.record_line_count")
    if records == 0:
        raise AdultAdapterError("MANIFEST_COUNTS", f"{source_file}.record_line_count")
    skipped = _array(section["skipped_lines"], f"{source_file}.skipped_lines")
    lines: list[int] = []
    for entry in skipped:
        entry = _shape(entry, ("line", "reason"), f"{source_file}.skipped_line")
        lines.append(_count(entry["line"], f"{source_file}.skipped_line.line", 1))
        if entry["reason"] not in _SKIP_REASONS:
            raise AdultAdapterError("MANIFEST_FILE", f"{source_file}.skip_reason")
        if entry["reason"] == "comment_header" and (source_file != TEST_SOURCE_FILE or entry["line"] != 1):
            raise AdultAdapterError("MANIFEST_FILE", f"{source_file}.comment_header")
    if lines != sorted(set(lines)) or any(n > physical for n in lines):
        raise AdultAdapterError("MANIFEST_FILE", f"{source_file}.skipped_lines")
    if records + len(lines) != physical:
        raise AdultAdapterError("MANIFEST_COUNTS", f"{source_file}.lines")
    ends = _shape(section["line_endings"], _ENDING_KEYS, f"{source_file}.line_endings")
    crlf = _count(ends["crlf_lines"], f"{source_file}.crlf_lines")
    lf = _count(ends["lf_only_lines"], f"{source_file}.lf_only_lines")
    unterminated = _count(ends["unterminated_lines"], f"{source_file}.unterminated_lines")
    if type(ends["final_newline"]) is not bool or unterminated > 1 or ends["final_newline"] != (unterminated == 0):
        raise AdultAdapterError("MANIFEST_FILE", f"{source_file}.final_newline")
    if crlf + lf + unterminated != physical:
        raise AdultAdapterError("MANIFEST_COUNTS", f"{source_file}.line_endings")
    return set(lines)


def _check_dups(block: Any, source_file: str, release: str, section: dict[str, Any], skipped: set[int]) -> dict[str, int]:
    block = _shape(block, _DUP_KEYS, f"{source_file}.duplicates")
    groups = _array(block["groups"], f"{source_file}.duplicates.groups")
    seen: set[int] = set()
    sizes: dict[str, int] = {}
    previous = ""
    for group in groups:
        group = _shape(group, ("group_key", "row_ids"), f"{source_file}.duplicate_group")
        key = digest_field(group["group_key"], "group_key")
        if key <= previous:
            raise AdultAdapterError("MANIFEST_DUPLICATES", "group_key order")
        previous = key
        lines = []
        for row_id in _array(group["row_ids"], f"{source_file}.row_ids"):
            parsed = parse_row_id(row_id)
            if (parsed.release, parsed.source_file) != (release, source_file):
                raise AdultAdapterError("MANIFEST_DUPLICATES", row_id)
            lines.append(parsed.line)
        if (
            len(lines) < 2 or lines != sorted(set(lines)) or seen & set(lines)
            or lines[-1] > section["physical_line_count"] or skipped & set(lines)
        ):
            raise AdultAdapterError("MANIFEST_DUPLICATES", key)
        seen.update(lines)
        sizes[key] = len(lines)
    counts = (
        _count(block["group_count_total"], "group_count_total"),
        _count(block["duplicate_group_count"], "duplicate_group_count"),
        _count(block["duplicate_row_count"], "duplicate_row_count"),
    )
    if counts[1:] != (len(groups), len(seen)):
        raise AdultAdapterError("MANIFEST_COUNTS", f"{source_file}.duplicates")
    if counts[0] > section["record_line_count"] or counts[0] < len(groups):
        raise AdultAdapterError("MANIFEST_COUNTS", f"{source_file}.group_count_total")
    # Every record is in exactly one group: singles + duplicate rows == records.
    if counts[0] - len(groups) + len(seen) != section["record_line_count"]:
        raise AdultAdapterError("MANIFEST_COUNTS", f"{source_file}.group_rows")
    return sizes


def _check_overlap(doc: dict[str, Any], train_sizes: dict[str, int], test_sizes: dict[str, int]) -> None:
    overlap = _shape(doc["overlap"], _OVERLAP_KEYS, "overlap")
    groups = _array(overlap["groups"], "overlap.groups")
    keys: list[str] = []
    train_total = test_total = 0
    for group in groups:
        group = _shape(group, ("group_key", "train_row_count", "test_row_count"), "overlap_group")
        key = digest_field(group["group_key"], "group_key")
        counts = (_count(group["train_row_count"], "train_row_count", 1), _count(group["test_row_count"], "test_row_count", 1))
        for count, sizes in zip(counts, (train_sizes, test_sizes)):
            # count >= 2 <=> the key is a duplicate group of exactly that size on that side.
            if (sizes.get(key) != count) if count >= 2 else (key in sizes):
                raise AdultAdapterError("MANIFEST_OVERLAP", key)
        keys.append(key)
        train_total += counts[0]
        test_total += counts[1]
    connected = _array(doc["test_connected_group_keys"], "test_connected_group_keys")
    if keys != sorted(set(keys)) or keys != connected:
        raise AdultAdapterError("MANIFEST_OVERLAP", "group_keys")
    declared = (
        _count(overlap["group_count"], "overlap.group_count"),
        _count(overlap["train_row_count"], "overlap.train_row_count"),
        _count(overlap["test_row_count"], "overlap.test_row_count"),
    )
    if declared != (len(keys), train_total, test_total):
        raise AdultAdapterError("MANIFEST_COUNTS", "overlap")
    if train_total > doc["train_file"]["record_line_count"] or test_total > doc["test_file"]["record_line_count"]:
        raise AdultAdapterError("MANIFEST_COUNTS", "overlap_rows")


def _verify_body(doc: dict[str, Any]) -> None:
    for key, expected in (("schema", MANIFEST_SCHEMA), ("label_policy", LABEL_POLICY), ("custodian_status", CUSTODIAN_STATUS)):
        if doc[key] != expected:
            raise AdultAdapterError("MANIFEST_FIELD", key)
    if doc["tool_versions"] != {
        "feature_group_version": FEATURE_GROUP_VERSION,
        "feature_schema_digest": ADULT_FEATURE_CONTRACT.schema_digest,
    }:
        raise AdultAdapterError("MANIFEST_FIELD", "tool_versions")
    release = doc["release"]
    make_row_id(release, DEVELOPMENT_SOURCE_FILE, 1)
    train_skipped = _check_file(doc["train_file"], DEVELOPMENT_SOURCE_FILE)
    if type(doc["duplicates"]) is not dict:
        raise AdultAdapterError("MANIFEST_SHAPE", "duplicates")
    train_dups = doc["duplicates"].get("train")
    train_sizes = _check_dups(train_dups, DEVELOPMENT_SOURCE_FILE, release, doc["train_file"], train_skipped)
    if doc["status"] == STATUS_TRAIN_ONLY:
        if (doc["test_file"], doc["overlap"], doc["test_connected_group_keys"]) != (None, None, None) or set(doc["duplicates"]) != {"train"}:
            raise AdultAdapterError("MANIFEST_STATUS", STATUS_TRAIN_ONLY)
        return
    if doc["status"] != STATUS_TRAIN_AND_TEST or None in (doc["test_file"], doc["overlap"], doc["test_connected_group_keys"]):
        raise AdultAdapterError("MANIFEST_STATUS", str(doc["status"]))
    test_skipped = _check_file(doc["test_file"], TEST_SOURCE_FILE)
    if set(doc["duplicates"]) != {"train", "test"}:
        raise AdultAdapterError("MANIFEST_STATUS", "duplicates")
    test_sizes = _check_dups(doc["duplicates"]["test"], TEST_SOURCE_FILE, release, doc["test_file"], test_skipped)
    _check_overlap(doc, train_sizes, test_sizes)


def verify_source_manifest(doc: Any) -> dict[str, Any]:
    """Recompute the self digest, require a closed schema and internal consistency.

    Returns ``doc`` or raises ``AdultAdapterError``; no other exception type escapes.
    This cannot detect a coherent forgery with a recomputed digest; see the module docstring
    and use ``verify_against_bytes`` for the real files.
    """
    if type(doc) is not dict or set(doc) != set(_BODY_KEYS) | {"manifest_sha256"}:
        raise AdultAdapterError("MANIFEST_KEYS", "manifest")
    body = {k: v for k, v in doc.items() if k != "manifest_sha256"}
    try:
        recomputed = canonical_digest(body)
    except (TypeError, ValueError, UnicodeError):
        raise AdultAdapterError("MANIFEST_DIGEST", "manifest_sha256") from None
    if digest_field(doc["manifest_sha256"], "manifest_sha256") != recomputed:
        raise AdultAdapterError("MANIFEST_DIGEST", "manifest_sha256")
    try:
        _verify_body(doc)
    except AdultAdapterError:
        raise
    except (KeyError, TypeError, AttributeError, IndexError, ValueError):  # safety net for unforeseen shapes
        raise AdultAdapterError("MANIFEST_SHAPE", "manifest") from None
    return doc


def _bytes_of(source: Any, name: str) -> bytes:
    if type(source) is bytes:
        return source
    if isinstance(source, (str, os.PathLike)):
        return Path(source).read_bytes()
    raise AdultAdapterError("FILE_BYTES", name)


def verify_against_bytes(doc: Any, train: Any, test: Any = None) -> dict[str, Any]:
    """Require ``build_source_manifest(train, test, doc['release']) == doc`` exactly.

    ``train``/``test`` are bytes or paths. For release ``uci-adult-2`` the rebuilt training
    sha256 and record count must also equal ``FROZEN_ADULT_SOURCE``.
    """
    verify_source_manifest(doc)
    train_bytes = _bytes_of(train, DEVELOPMENT_SOURCE_FILE)
    test_bytes = None if test is None else _bytes_of(test, TEST_SOURCE_FILE)
    rebuilt = build_source_manifest(train_bytes, test_bytes, doc["release"])
    if rebuilt != doc:
        raise AdultAdapterError("MANIFEST_MISMATCH", "rebuilt manifest differs")
    if doc["release"] == FROZEN_RELEASE and (
        rebuilt["train_file"]["sha256"] != FROZEN_ADULT_SOURCE["raw_sha256"]
        or rebuilt["train_file"]["record_line_count"] != FROZEN_ADULT_SOURCE["raw_records"]
    ):
        raise AdultAdapterError("FROZEN_MISMATCH", "train file differs from FROZEN_ADULT_SOURCE")
    return doc


def connected_group_key_set(doc: dict[str, Any], train: Any, test: Any) -> frozenset[str]:
    """Test-connected keys as a frozenset for ``grouping.quarantine_test_connected``.

    Requires the source bytes/paths and the exact rebuild check (``verify_against_bytes``).
    """
    if test is None:
        raise AdultAdapterError("NO_TEST_FILE", "test")
    verify_against_bytes(doc, train, test)
    return frozenset(doc["test_connected_group_keys"])


def manifest_text(doc: dict[str, Any]) -> str:
    """Canonical JSON of a self-verified manifest."""
    return canonical_json(verify_source_manifest(doc))
