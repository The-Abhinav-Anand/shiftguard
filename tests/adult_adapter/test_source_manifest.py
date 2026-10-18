"""Label-blind Adult source manifest: fabricated rows only, written under tmp_path."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from shiftguard.adult_adapter.features import (
    AdultAdapterError, AdultRecord, canonical_digest, make_row_id, record_from_raw_fields)
from shiftguard.adult_adapter.grouping import group_key, quarantine_test_connected
from shiftguard.adult_adapter.source_manifest import (
    FROZEN_RELEASE,
    LABEL_POLICY,
    build_source_manifest,
    connected_group_key_set,
    manifest_text,
    verify_against_bytes,
    verify_source_manifest,
)
from shiftguard.datasets.adult import ADULT_PREDICTORS, FROZEN_ADULT_SOURCE, clean_adult_rows

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "adult_build_source_manifest.py"
REL = "uci-adult-test"
FROZEN = "uci-adult-2"


def row(age: int, work: str = "Private", label: bytes = b"<=50K") -> bytes:
    feats = f"{age}, {work}, 100{age}, Bachelors, 13, Never-married, Sales, Husband, White, Male, 0, 0, 40, ?".encode()
    return feats + b", " + label


def join(lines: list[bytes], eol: bytes = b"\n", tail: bytes = b"\n") -> bytes:
    return eol.join(lines) + tail


def err(fn, *a) -> str:
    with pytest.raises(AdultAdapterError) as info:
        fn(*a)
    return info.value.code


def test_accounting_header_blank_lines():
    train = join([row(30), b"", row(31), row(30)], tail=b"\n\n")
    test = join([b"|1x3 Cross validator", row(30, label=b"<=50K."), b"   ", row(40)])
    doc = build_source_manifest(train, test, REL)
    t, s = doc["train_file"], doc["test_file"]
    assert (t["byte_size"], t["sha256"]) == (len(train), hashlib.sha256(train).hexdigest())
    assert (t["physical_line_count"], t["record_line_count"]) == (5, 3)
    assert t["skipped_lines"] == [{"line": 2, "reason": "blank"}, {"line": 5, "reason": "blank"}]
    assert (s["physical_line_count"], s["record_line_count"]) == (4, 2)
    assert s["skipped_lines"] == [{"line": 1, "reason": "comment_header"}, {"line": 3, "reason": "blank"}]
    assert doc["status"] == "train_and_test" and doc["custodian_status"] == "author-built, not custodian-attested"
    assert doc["label_policy"] == LABEL_POLICY == (
        "label field never decoded, compared or counted; label bytes enter only whole-file "
        "byte_size/sha256, the field-count check and line-terminator detection")
    assert verify_source_manifest(doc) is doc
    assert doc["manifest_sha256"] == hashlib.sha256(
        json.dumps({k: v for k, v in doc.items() if k != "manifest_sha256"}, sort_keys=True,
                   separators=(",", ":")).encode()).hexdigest()


def test_header_only_on_first_line_and_unterminated_last_line():
    assert err(build_source_manifest, join([row(30), b"|x"]), None, REL) == "FIELD_COUNT"
    # a '|' header is allowed in adult.test line 1 only
    assert err(build_source_manifest, join([b"|1x3 Cross validator", row(30)]), None, REL) == "HEADER_IN_TRAIN"
    assert err(build_source_manifest, join([row(30)]), join([row(30), b"|x"]), REL) == "FIELD_COUNT"
    doc = build_source_manifest(row(30), None, REL)  # no trailing newline
    assert doc["train_file"]["physical_line_count"] == 1
    assert doc["train_file"]["line_endings"] == {
        "crlf_lines": 0, "lf_only_lines": 0, "unterminated_lines": 1, "final_newline": False}
    assert err(build_source_manifest, b"\n \n", None, REL) == "NO_RECORDS"
    assert err(build_source_manifest, join([row(30)]), b"|only a header\n", REL) == "NO_RECORDS"


def test_field_count_errors_are_typed():
    assert err(build_source_manifest, join([row(30)[:-8]]), None, REL) == "FIELD_COUNT"
    assert err(build_source_manifest, join([row(30) + b", extra"]), None, REL) == "FIELD_COUNT"
    # a label containing a comma changes the count: rejected, never parsed
    assert err(build_source_manifest, join([row(30, label=b"a,b")]), None, REL) == "FIELD_COUNT"
    assert err(build_source_manifest, join([row(30).replace(b"Private", b"")]), None, REL) == "EMPTY_TOKEN"
    assert err(build_source_manifest, join([row(30).replace(b"Private", b"Pr\xc3\xafvate")]), None, REL) == "NON_ASCII_FEATURE"
    assert err(build_source_manifest, b"a\rb\n", None, REL) == "FIELD_COUNT"
    for bad in (b"\x00", b"\x01", b"\x1b", b"\x7f"):
        assert err(build_source_manifest, join([row(30).replace(b"Sales", b"Sa" + bad + b"les")]), None, REL) == "CONTROL_BYTE"
    tabbed = build_source_manifest(join([row(30).replace(b"Sales", b"Sa\tles")]), None, REL)
    assert tabbed["train_file"]["record_line_count"] == 1
    # a bare CR inside the label slot is never inspected
    assert build_source_manifest(join([row(30, label=b"a\rb")]), None, REL)["train_file"]["record_line_count"] == 1
    assert err(build_source_manifest, join([row(30).replace(b"Sales", b"Sa\rles")]), None, REL) == "BARE_CR"
    assert err(build_source_manifest, row(30), None, "bad release!") == "ROW_ID"


def test_duplicate_and_overlap_groups_and_ids():
    train = join([row(30), row(31), row(30), row(30), row(50)])
    test = join([b"|1x3 Cross validator", row(30), row(30), row(60), row(50)])
    doc = build_source_manifest(train, test, REL)
    td = doc["duplicates"]["train"]
    assert td["duplicate_group_count"] == 1 and td["duplicate_row_count"] == 3 and td["group_count_total"] == 3
    assert td["groups"][0]["row_ids"] == [f"{REL}:adult.data:{n}" for n in (1, 3, 4)]
    assert doc["duplicates"]["test"]["groups"][0]["row_ids"] == [f"{REL}:adult.test:2", f"{REL}:adult.test:3"]
    assert doc["overlap"]["group_count"] == 2
    assert doc["overlap"]["train_row_count"] == 4 and doc["overlap"]["test_row_count"] == 3
    # group key agrees with grouping.group_key over an adapter-built record
    names = [n for n in ADULT_PREDICTORS]
    vals = ["30", "Private", "10030", "13", "Never-married", "Sales", "Husband", "White", "Male", "0", "0", "40", "?"]
    rec = record_from_raw_fields(make_row_id(REL, "adult.data", 1), dict(zip(names, vals)))
    assert group_key(rec) in doc["test_connected_group_keys"]
    assert doc["test_connected_group_keys"] == sorted(doc["test_connected_group_keys"])


def test_train_only_status():
    doc = build_source_manifest(join([row(30)]), None, REL)
    assert doc["status"] == "train_only"
    assert doc["test_file"] is None and doc["overlap"] is None and doc["test_connected_group_keys"] is None
    verify_source_manifest(doc)
    assert err(lambda: connected_group_key_set(doc, join([row(30)]), None, expected_release=FROZEN)) == "NO_TEST_FILE"


LABEL_VARIANTS = [b">50K", b"<=50K.", b">50K.", b"", b"zzz", b"\xff\xfe\x00\x80 not text", b"  <=50K \t", b"a\rb"]
AGES = [30, 31, 30, 45, 50, 31, 60, 30]


def labelled_file(labels, suffix=b"", header=False):
    lines = [b"|1x3 Cross validator"] if header else []
    lines += [row(age, label=labels[i % len(labels)]) + suffix for i, age in enumerate(AGES)]
    return join(lines)


# Fields that may legitimately change when only labels / terminators change: file identity
# (the bytes cover labels) and, for the trailing-CR variant, the line_endings tallies.
IDENTITY_ONLY = ("byte_size", "sha256")


def stripped(doc, endings=False):
    doc = copy.deepcopy(doc)
    for part in ("train_file", "test_file"):
        for key in IDENTITY_ONLY:
            doc[part].pop(key)
        if endings:
            doc[part].pop("line_endings")
    del doc["manifest_sha256"]
    return json.dumps(doc, sort_keys=True)


@pytest.mark.parametrize("variant", range(len(LABEL_VARIANTS)))
def test_label_invariance_per_row_varied_labels(variant):
    base_labels = [b"<=50K", b">50K", b"<=50K", b">50K", b"<=50K", b"<=50K", b">50K", b"<=50K"]
    varied = [LABEL_VARIANTS[(variant + i) % len(LABEL_VARIANTS)] for i in range(len(AGES))]
    base = build_source_manifest(labelled_file(base_labels), labelled_file(base_labels, header=True), REL)
    other = build_source_manifest(labelled_file(varied), labelled_file(varied, header=True), REL)
    assert stripped(base) == stripped(other)
    assert base["train_file"]["sha256"] != other["train_file"]["sha256"]


def test_label_invariance_trailing_cr_variant():
    labels = [b"<=50K", b">50K."]
    lf = build_source_manifest(labelled_file(labels), labelled_file(labels, header=True), REL)
    cr = build_source_manifest(labelled_file(labels, suffix=b"\r"), labelled_file(labels, suffix=b"\r", header=True), REL)
    # Legitimate changes: byte_size, sha256 and the line_endings tallies (CRLF vs LF), nothing else.
    assert stripped(lf, endings=True) == stripped(cr, endings=True)
    assert cr["train_file"]["line_endings"]["crlf_lines"] == len(AGES)
    assert cr["test_file"]["line_endings"]["crlf_lines"] == len(AGES)  # the header line stays LF-only
    assert lf["train_file"]["line_endings"]["crlf_lines"] == 0


def test_no_feature_region_length_in_manifest():
    doc = build_source_manifest(join([row(30)]), join([b"|h", row(30)]), REL)

    def names(node):
        if isinstance(node, dict):
            for key, value in node.items():
                yield key
                yield from names(value)
        elif isinstance(node, list):
            for value in node:
                yield from names(value)

    banned = ("length", "feature_byte", "feature_size", "region", "line_size", "line_bytes")
    assert not [n for n in names(doc) if any(b in n for b in banned)]
    assert [n for n in names(doc) if "size" in n or "bytes" in n] == ["byte_size", "byte_size"]


def test_cross_check_against_clean_adult_rows():
    data = join([row(30), b"", row(31, "State-gov"), row(30), row(45), b"   ", row(31, "State-gov"), row(50)])
    doc = build_source_manifest(data, None, REL)
    cleaned = clean_adult_rows(data.decode("ascii").splitlines())
    skipped = {s["line"] for s in doc["train_file"]["skipped_lines"]}
    record_lines = [n for n in range(1, doc["train_file"]["physical_line_count"] + 1) if n not in skipped]
    assert len(cleaned) == doc["train_file"]["record_line_count"] == len(record_lines)
    ordinal = {line: i for i, line in enumerate(record_lines)}  # i-th record <-> i-th cleaned row

    def features(index):
        return tuple((k, v) for k, v in cleaned[index].items() if k not in ("row_id", "income"))

    dup = doc["duplicates"]["train"]
    in_dup = set()
    for group in dup["groups"]:
        group_lines = [int(r.rsplit(":", 1)[1]) for r in group["row_ids"]]
        in_dup.update(group_lines)
        assert len({features(ordinal[n]) for n in group_lines}) == 1
    assert in_dup == {1, 4, 3, 7}  # lines of the two duplicated feature vectors
    assert len({features(i) for i in range(len(cleaned))}) == dup["group_count_total"]


def test_trailing_cr_on_unterminated_last_line_is_label_slot_and_not_crlf():
    base = join([row(30), row(31, "State-gov")], tail=b"")  # last line unterminated
    cr = base + b"\r"  # bytes end in CR with no LF
    a, b = build_source_manifest(base, None, REL), build_source_manifest(cr, None, REL)
    assert b == build_source_manifest(cr, None, REL)  # deterministic
    # The CR is not a terminator: it sits in the unread label slot, is not a CRLF line and changes
    # nothing but whole-file identity.
    assert b["train_file"]["line_endings"] == {
        "crlf_lines": 0, "lf_only_lines": 1, "unterminated_lines": 1, "final_newline": False}
    assert b["train_file"]["sha256"] == hashlib.sha256(cr).hexdigest() != a["train_file"]["sha256"]
    identity = ("byte_size", "sha256")
    assert (
        {k: v for k, v in a["train_file"].items() if k not in identity}
        == {k: v for k, v in b["train_file"].items() if k not in identity}
    )
    assert a["duplicates"] == b["duplicates"]
    assert a["train_file"]["record_group_digest"] == b["train_file"]["record_group_digest"]
    verify_source_manifest(b)
    # a lone CR as the whole unterminated last line is whitespace-only, hence blank
    lone = build_source_manifest(join([row(30)]) + b"\r", None, REL)
    assert lone["train_file"]["skipped_lines"] == [{"line": 2, "reason": "blank"}]
    assert lone["train_file"]["line_endings"]["crlf_lines"] == 0
    # ...and, against the same file without it, adds one blank unterminated physical line
    plain = build_source_manifest(join([row(30)]), None, REL)
    assert plain["train_file"]["physical_line_count"] == 1 and plain["train_file"]["skipped_lines"] == []
    assert lone["train_file"]["physical_line_count"] == 2
    assert plain["train_file"]["line_endings"]["unterminated_lines"] == 0
    assert lone["train_file"]["line_endings"]["unterminated_lines"] == 1
    assert plain["train_file"]["line_endings"]["final_newline"] and not lone["train_file"]["line_endings"]["final_newline"]
    # a CR that lands in the feature region of an unterminated last line is still BARE_CR
    assert err(build_source_manifest, row(30).replace(b"Private", b"Priv\rate"), None, REL) == "BARE_CR"


def test_crlf_equals_lf_for_parsing_but_bytes_hash_as_is():
    lines = [row(30), b"", row(31)]
    lf, crlf = join(lines), join(lines, eol=b"\r\n", tail=b"\r\n")
    a, b = build_source_manifest(lf, None, REL), build_source_manifest(crlf, None, REL)
    assert a["train_file"]["sha256"] != b["train_file"]["sha256"]
    assert a["train_file"]["sha256"] == hashlib.sha256(lf).hexdigest()
    assert b["train_file"]["sha256"] == hashlib.sha256(crlf).hexdigest()
    assert b["train_file"]["line_endings"] == {
        "crlf_lines": 3, "lf_only_lines": 0, "unterminated_lines": 0, "final_newline": True}
    assert a["train_file"]["line_endings"]["crlf_lines"] == 0
    assert a["train_file"]["record_group_digest"] == b["train_file"]["record_group_digest"]
    assert a["duplicates"] == b["duplicates"]
    assert a["train_file"]["skipped_lines"] == b["train_file"]["skipped_lines"]


def _pin_fabricated_frozen(monkeypatch, train, records):
    """Point the frozen-source pin at fabricated bytes so the frozen path is exercisable."""
    monkeypatch.setitem(FROZEN_ADULT_SOURCE, "raw_sha256", hashlib.sha256(train).hexdigest())
    monkeypatch.setitem(FROZEN_ADULT_SOURCE, "raw_records", records)


def test_frozen_release_matches_dataset_id():
    assert FROZEN == FROZEN_RELEASE == FROZEN_ADULT_SOURCE["dataset_id"]


def test_unreadable_source_path_is_typed(tmp_path):
    doc = build_source_manifest(join([row(30)]), None, REL)
    assert err(verify_against_bytes, doc, tmp_path, None) == "SOURCE_UNREADABLE"


def test_connected_group_key_set_enforces_frozen_release(monkeypatch):
    train = join([row(30), row(31)])
    test = join([b"|1x3 Cross validator", row(30)])

    def call(doc, **kw):
        return err(lambda: connected_group_key_set(doc, train, test, **kw))

    with pytest.raises(TypeError):  # the keyword is required
        connected_group_key_set(build_source_manifest(train, test, FROZEN), train, test)
    other = build_source_manifest(train, test, REL)
    # a non-frozen release can neither be expected nor bypass the pin by matching its own name
    assert call(other, expected_release=REL) == "RELEASE_NOT_FROZEN"
    assert call(other, expected_release=FROZEN) == "RELEASE_MISMATCH"
    assert call(other, expected_release="") == "RELEASE_NOT_FROZEN"
    assert call(other, expected_release=None) == "RELEASE_NOT_FROZEN"
    frozen = build_source_manifest(train, test, FROZEN)
    assert call(frozen, expected_release=REL) == "RELEASE_NOT_FROZEN"
    assert call({}, expected_release=FROZEN) == "MANIFEST_KEYS"
    # frozen release with bytes that are not the pinned archive: the pin refuses
    assert call(frozen, expected_release=FROZEN) == "FROZEN_MISMATCH"
    _pin_fabricated_frozen(monkeypatch, train, 2)
    assert connected_group_key_set(frozen, train, test, expected_release=FROZEN) == frozenset(frozen["test_connected_group_keys"])


def test_quarantine_interoperability(monkeypatch):
    train = join([row(30), row(31), row(30), row(50)])
    test = join([b"|1x3 Cross validator", row(30), row(70)])
    _pin_fabricated_frozen(monkeypatch, train, 4)
    doc = build_source_manifest(train, test, FROZEN)
    keys = connected_group_key_set(doc, train, test, expected_release=FROZEN)
    assert err(lambda: connected_group_key_set(doc, train, join([row(99)]), expected_release=FROZEN)) == "MANIFEST_MISMATCH"
    assert isinstance(keys, frozenset)
    recs = []
    for n, age in enumerate((30, 31, 30, 50), start=1):
        vals = [str(age), "Private", f"100{age}", "13", "Never-married", "Sales", "Husband", "White", "Male", "0", "0", "40", "?"]
        recs.append(record_from_raw_fields(make_row_id(FROZEN, "adult.data", n), dict(zip(ADULT_PREDICTORS, vals))))
    result = quarantine_test_connected(tuple(recs), keys)
    assert result.quarantined_row_ids == (f"{FROZEN}:adult.data:1", f"{FROZEN}:adult.data:3")
    assert result.declared_groups_absent_count == 0 and result.retained_row_count == 2
    assert isinstance(recs[0], AdultRecord)


def redigest(d):
    d["manifest_sha256"] = canonical_digest({k: v for k, v in d.items() if k != "manifest_sha256"})
    return d


def _good():
    train = join([row(30), row(30), row(31), row(31), row(31), row(40)])
    test = join([b"|1x3 Cross validator", row(30), row(31), row(31), row(31), row(70)])
    return train, test, build_source_manifest(train, test, REL)


def test_digest_verification_detects_tampering():
    train, test, doc = _good()
    verify_source_manifest(doc)
    bad = copy.deepcopy(doc)
    bad["train_file"]["record_line_count"] += 1
    assert err(verify_source_manifest, bad) == "MANIFEST_DIGEST"
    bad = copy.deepcopy(doc)
    bad["train_file"]["record_line_count"] += 1
    assert err(verify_source_manifest, redigest(bad)) == "MANIFEST_COUNTS"
    bad = copy.deepcopy(doc)
    bad["test_connected_group_keys"] = []
    assert err(verify_source_manifest, redigest(bad)) == "MANIFEST_OVERLAP"
    bad = copy.deepcopy(doc)
    bad["custodian_status"] = "custodian-attested"
    assert err(verify_source_manifest, redigest(bad)) == "MANIFEST_FIELD"
    bad = copy.deepcopy(doc)
    bad["extra"] = 1
    assert err(verify_source_manifest, bad) == "MANIFEST_KEYS"


def mutate(doc, path, value):
    bad = copy.deepcopy(doc)
    node = bad
    for step in path[:-1]:
        node = node[step]
    if value is _DELETE:
        del node[path[-1]]
    else:
        node[path[-1]] = value
    return redigest(bad)


_DELETE = object()
SHAPE_CASES = [
    # (path, value): every nesting level, wrong types, extra and missing keys
    (("train_file", "extra"), 1),
    (("train_file", "byte_size"), _DELETE),
    (("train_file", "byte_size"), True),
    (("train_file", "byte_size"), 5.0),
    (("train_file", "physical_line_count"), 6.0),
    (("train_file", "line_endings"), []),
    (("train_file", "line_endings", "extra"), 1),
    (("train_file", "line_endings", "crlf_lines"), False),
    (("train_file", "line_endings", "unterminated_lines"), None),
    (("train_file", "line_endings", "final_newline"), 1),
    (("train_file", "line_endings", "final_newline"), "yes"),
    (("train_file", "skipped_lines"), {}),
    (("train_file", "skipped_lines"), "x"),
    (("test_file", "skipped_lines"), [None]),
    (("test_file", "skipped_lines"), [{"line": 1}]),
    (("test_file", "skipped_lines"), [{"line": True, "reason": "comment_header"}]),
    (("test_file", "skipped_lines"), [{"line": 1, "reason": "comment_header", "x": 1}]),
    (("test_file", "skipped_lines"), [{"line": 2, "reason": "comment_header"}]),
    (("test_file", "skipped_lines"), [{"line": 1, "reason": "other"}]),
    (("test_file", "name"), "adult.data"),
    (("test_file",), []),
    (("train_file",), None),
    (("duplicates",), []),
    (("duplicates", "extra"), {}),
    (("duplicates", "train"), None),
    (("duplicates", "train", "extra"), 1),
    (("duplicates", "train", "groups"), None),
    (("duplicates", "train", "groups"), [1]),
    (("duplicates", "train", "groups", 0, "extra"), 1),
    (("duplicates", "train", "groups", 0, "row_ids"), "ab"),
    (("duplicates", "train", "groups", 0, "row_ids"), [3]),
    (("duplicates", "train", "groups", 0, "group_key"), 7),
    (("duplicates", "train", "duplicate_group_count"), 2.0),
    (("duplicates", "train", "duplicate_row_count"), True),
    (("overlap",), []),
    (("overlap", "extra"), 1),
    (("overlap", "groups"), None),
    (("overlap", "groups"), [[]]),
    (("overlap", "groups", 0, "extra"), 1),
    (("overlap", "groups", 0, "train_row_count"), True),
    (("overlap", "groups", 0, "test_row_count"), 1.0),
    (("overlap", "group_count"), True),
    (("test_connected_group_keys",), None),
    (("test_connected_group_keys",), "abc"),
    (("tool_versions",), []),
    (("release",), 5),
    (("status",), ["train_only"]),
]


@pytest.mark.parametrize("path,value", SHAPE_CASES)
def test_closed_schema_rejections_are_typed(path, value):
    _, _, doc = _good()
    assert err(verify_source_manifest, mutate(doc, list(path), value)) in {
        "MANIFEST_SHAPE", "MANIFEST_FILE", "MANIFEST_COUNTS", "MANIFEST_DUPLICATES", "MANIFEST_OVERLAP",
        "MANIFEST_STATUS", "MANIFEST_FIELD", "ROW_ID", "DIGEST",
    }


def test_non_dict_inputs_are_typed():
    for value in (None, [], "x", 3):
        assert err(verify_source_manifest, value) == "MANIFEST_KEYS"


def test_overlap_counts_agree_with_duplicate_groups():
    _, _, doc = _good()
    # key for age 31 appears 3x per side (duplicate group); age 30: 2 train rows, 1 test row
    by_count = {(g["train_row_count"], g["test_row_count"]) for g in doc["overlap"]["groups"]}
    assert by_count == {(2, 1), (3, 3)}
    bad = copy.deepcopy(doc)
    for g in bad["overlap"]["groups"]:
        if g["test_row_count"] == 3:
            g["test_row_count"] = 2  # claims size 2, duplicate block says 3
    bad["overlap"]["test_row_count"] -= 1
    assert err(verify_source_manifest, redigest(bad)) == "MANIFEST_OVERLAP"
    bad = copy.deepcopy(doc)
    for g in bad["overlap"]["groups"]:
        if g["test_row_count"] == 1:
            g["test_row_count"] = 2  # claims a duplicate group that does not exist
    bad["overlap"]["test_row_count"] += 1
    assert err(verify_source_manifest, redigest(bad)) == "MANIFEST_OVERLAP"


def test_duplicate_row_ids_must_not_point_at_skipped_lines():
    train = join([row(30), b"", row(30)])
    doc = build_source_manifest(train, None, REL)
    assert doc["duplicates"]["train"]["groups"][0]["row_ids"][-1].endswith(":3")
    bad = copy.deepcopy(doc)
    bad["duplicates"]["train"]["groups"][0]["row_ids"][-1] = f"{REL}:adult.data:2"  # the blank line
    assert err(verify_source_manifest, redigest(bad)) == "MANIFEST_DUPLICATES"


def test_header_comment_only_line_one_of_test_file():
    doc = build_source_manifest(join([row(30)]), join([b"|h", row(30)]), REL)
    bad = mutate(doc, ["train_file", "skipped_lines"], [{"line": 1, "reason": "comment_header"}])
    assert err(verify_source_manifest, bad) == "MANIFEST_FILE"


def test_zero_records_rejected_by_verify():
    doc = build_source_manifest(join([row(30)]), None, REL)
    bad = copy.deepcopy(doc)
    bad["train_file"]["record_line_count"] = 0
    bad["train_file"]["skipped_lines"] = []
    bad["train_file"]["physical_line_count"] = 0
    bad["train_file"]["line_endings"] = {"crlf_lines": 0, "lf_only_lines": 0, "unterminated_lines": 0, "final_newline": True}
    bad["duplicates"]["train"] = {"group_count_total": 0, "duplicate_group_count": 0, "duplicate_row_count": 0, "groups": []}
    assert err(verify_source_manifest, redigest(bad)) == "MANIFEST_COUNTS"


def test_verify_against_bytes(tmp_path):
    train, test, doc = _good()
    assert verify_against_bytes(doc, train, test) is doc
    (tmp_path / "t.data").write_bytes(train)
    (tmp_path / "t.test").write_bytes(test)
    assert verify_against_bytes(doc, tmp_path / "t.data", str(tmp_path / "t.test")) is doc
    assert err(verify_against_bytes, doc, train, None) == "MANIFEST_MISMATCH"
    assert err(verify_against_bytes, doc, train + b"\n", test) == "MANIFEST_MISMATCH"
    assert err(verify_against_bytes, doc, 12, test) == "FILE_BYTES"
    assert err(verify_against_bytes, doc, tmp_path / "absent.data", test) == "SOURCE_MISSING"
    assert err(verify_against_bytes, doc, train, str(tmp_path / "absent.test")) == "SOURCE_MISSING"
    assert err(verify_against_bytes, doc, train.replace(b"Private", b"Privat3"), test) == "MANIFEST_MISMATCH"
    # a coherent forgery passes self-verification but not the rebuild
    forged = copy.deepcopy(doc)
    forged["train_file"]["sha256"] = "0" * 64
    redigest(forged)
    assert verify_source_manifest(forged) is forged
    assert err(verify_against_bytes, forged, train, test) == "MANIFEST_MISMATCH"


def test_frozen_release_pins_training_file():
    train = join([row(30), row(31)])
    doc = build_source_manifest(train, None, "uci-adult-2")
    assert err(verify_against_bytes, doc, train, None) == "FROZEN_MISMATCH"
    assert FROZEN_ADULT_SOURCE["raw_records"] == 32561
    other = build_source_manifest(train, None, "uci-adult-other")
    assert verify_against_bytes(other, train, None) is other


def _load_script():
    spec = importlib.util.spec_from_file_location("adult_build_source_manifest", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(*args: str):
    return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], capture_output=True, text=True, cwd=ROOT)


def test_script_writes_and_refuses_overwrite(tmp_path):
    data, test, out = tmp_path / "adult.data", tmp_path / "adult.test", tmp_path / "m.json"
    data.write_bytes(join([row(30), row(30)]))
    test.write_bytes(join([b"|1x3 Cross validator", row(30)]))
    done = run("--data", str(data), "--test", str(test), "--release", REL, "--out", str(out))
    assert done.returncode == 0, done.stderr
    doc = json.loads(out.read_text("ascii"))
    verify_against_bytes(doc, data, test)
    assert doc["manifest_sha256"] in done.stdout
    assert "Private" not in done.stdout and "50K" not in done.stdout
    again = run("--data", str(data), "--release", REL, "--out", str(out))
    assert again.returncode == 2 and "OUTPUT_EXISTS" in again.stderr
    assert json.loads(out.read_text("ascii")) == doc
    bad = tmp_path / "bad.data"
    bad.write_bytes(b"1,2,3\n")
    failed = run("--data", str(bad), "--release", REL, "--out", str(tmp_path / "x.json"))
    assert failed.returncode == 2 and "FIELD_COUNT" in failed.stderr and not (tmp_path / "x.json").exists()


def test_script_refuses_docs_output_in_process(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "path", list(sys.path))  # the script inserts ROOT into sys.path; restore on exit
    script = _load_script()
    data = tmp_path / "adult.data"
    data.write_bytes(join([row(30)]))
    calls = []
    monkeypatch.setattr(script, "_write_exclusive", lambda *a, **k: calls.append(a))
    for target in (ROOT / "docs" / "nope" / "m.json", ROOT / "docs" / "m.json", ROOT / "x" / ".." / "docs" / "m.json"):
        assert script.main(["--data", str(data), "--release", REL, "--out", str(target)]) == 2
    assert "OUTPUT_UNDER_DOCS" in capsys.readouterr().err
    assert calls == []
    assert script.main(["--data", str(data), "--release", REL, "--out", str(tmp_path / "ok.json")]) == 0
    assert len(calls) == 1  # writer reached only for the non-docs path (and was stubbed)
