"""Gate 9 Adult adapter: feature contract, record parsing and import isolation.

Every row here is fabricated inside the test. No Adult file, manifest or
dataset directory is read, and no label is ever attached to an adapter record.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from shiftguard.adult_adapter import features as feat
from shiftguard.adult_adapter.features import (
    ADULT_FEATURE_CONTRACT,
    AdultAdapterError,
    AdultFeatureContract,
    make_row_id,
    parse_row_id,
    record_from_raw_fields,
)
from shiftguard.datasets import adult as parser


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def forbid_real_adult_paths(monkeypatch):
    # clean_adult_rows is deliberately NOT blocked: the parity test feeds it one fabricated line.
    def tripwire(name):
        def raiser(*_args, **_kwargs):
            raise AssertionError(f"adapter test reached {name}")
        return raiser

    for name in ("make_adult_role_splits", "acquire_adult_train_only", "execute_adult_confirmatory"):
        monkeypatch.setattr(parser, name, tripwire(name))


def fabricated_fields(i: int = 1, **overrides: str) -> dict[str, str]:
    values = {
        "age": str(20 + i % 50),
        "workclass": "Private",
        "fnlwgt": str(100000 + i),
        "education-num": "9",
        "marital-status": "Never-married",
        "occupation": "Sales",
        "relationship": "Not-in-family",
        "race": "White",
        "sex": "Male",
        "capital-gain": "0",
        "capital-loss": "0",
        "hours-per-week": "40",
        "native-country": "United-States",
    }
    values.update(overrides)
    return values


def test_contract_features_equal_the_parser_thirteen():
    contract = ADULT_FEATURE_CONTRACT
    assert contract.features == parser.ADULT_PREDICTORS
    assert len(contract.features) == 13
    assert "education" not in contract.features
    assert "income" not in contract.features
    assert contract.numeric == parser.ADULT_NUMERIC_FEATURES
    assert contract.categorical == parser.ADULT_CATEGORICAL_FEATURES
    assert set(contract.numeric) | set(contract.categorical) == set(contract.features)
    assert not set(contract.numeric) & set(contract.categorical)
    assert contract.natural_missing_token == "?"


def test_contract_matches_the_parser_on_one_fabricated_line():
    line = "39, ?, 77516, Bachelors, 13, Never-married, ?, Not-in-family, White, Male, 2174, 0, 40, United-States, <=50K"
    [parsed] = parser.clean_adult_rows([line])
    assert tuple(k for k in parsed if k not in ("row_id", "income")) == ADULT_FEATURE_CONTRACT.features
    fields = dict(zip(parser.RAW_ADULT_COLUMNS, [p.strip() for p in line.split(",")], strict=True))
    record = record_from_raw_fields("uci-adult-2:adult.data:1", {k: fields[k] for k in parser.ADULT_PREDICTORS})
    for name, token in zip(ADULT_FEATURE_CONTRACT.features, record.tokens, strict=True):
        # The parser nulls '?' and keeps every other value; only numeric spelling is lost there.
        assert (parsed[name] is None) == (token is None)
        if token is not None and name not in ADULT_FEATURE_CONTRACT.numeric:
            assert parsed[name] == token


def test_contract_and_records_are_immutable():
    with pytest.raises(dataclasses.FrozenInstanceError):
        ADULT_FEATURE_CONTRACT.features = ()  # type: ignore[misc]
    record = record_from_raw_fields("r:adult.data:1", fabricated_fields())
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.tokens = ()  # type: ignore[misc]
    assert type(record.tokens) is tuple
    assert type(ADULT_FEATURE_CONTRACT.features) is tuple


def test_schema_digest_is_canonical_and_sensitive_to_the_declaration():
    expected = hashlib.sha256(json.dumps({
        "schema_version": feat.SCHEMA_VERSION,
        "features": list(parser.ADULT_PREDICTORS),
        "numeric": list(parser.ADULT_NUMERIC_FEATURES),
        "categorical": list(parser.ADULT_CATEGORICAL_FEATURES),
        "natural_missing_token": "?",
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest()
    assert ADULT_FEATURE_CONTRACT.schema_digest == expected
    other = dataclasses.replace(ADULT_FEATURE_CONTRACT, natural_missing_token="NA")
    assert other.schema_digest != expected


@pytest.mark.parametrize("change", [
    {"numeric": ("not-a-feature",)},
    {"categorical": ()},
    {"features": ADULT_FEATURE_CONTRACT.features + ("age",)},
    {"natural_missing_token": ""},
])
def test_invalid_contract_declarations_are_rejected(change):
    with pytest.raises(AdultAdapterError) as caught:
        dataclasses.replace(ADULT_FEATURE_CONTRACT, **change)
    assert caught.value.code == "FEATURE_CONTRACT"


def test_question_mark_becomes_null_and_literals_are_preserved():
    record = record_from_raw_fields(
        "r:adult.data:3",
        fabricated_fields(workclass="?", occupation="  Sales ", age="39", **{"hours-per-week": "40"}),
    )
    tokens = dict(zip(ADULT_FEATURE_CONTRACT.features, record.tokens, strict=True))
    assert tokens["workclass"] is None
    assert tokens["occupation"] == "Sales"  # parser strips surrounding whitespace
    assert tokens["age"] == "39"
    # A literal 'Unknown' is a value, not a missing marker.
    literal = record_from_raw_fields("r:adult.data:4", fabricated_fields(workclass="Unknown"))
    assert literal.tokens[1] == "Unknown"


def test_token_order_follows_the_contract_not_the_mapping_order():
    fields = fabricated_fields()
    reordered = dict(reversed(list(fields.items())))
    a = record_from_raw_fields("r:adult.data:1", fields)
    b = record_from_raw_fields("r:adult.data:1", reordered)
    assert a.tokens == b.tokens


@pytest.mark.parametrize("mutate, code", [
    (lambda f: f.pop("race"), "MISSING_FIELD"),
    (lambda f: f.update(income="<=50K"), "UNEXPECTED_FIELD"),
    (lambda f: f.update(education="Bachelors"), "UNEXPECTED_FIELD"),
    (lambda f: f.update(age=39), "TOKEN_TYPE"),
    (lambda f: f.update(age=None), "TOKEN_TYPE"),
    (lambda f: f.update(sex=""), "EMPTY_TOKEN"),
    (lambda f: f.update(sex="   "), "EMPTY_TOKEN"),
])
def test_record_boundary_rejects_labels_extras_and_malformed_tokens(mutate, code):
    fields = fabricated_fields()
    mutate(fields)
    with pytest.raises(AdultAdapterError) as caught:
        record_from_raw_fields("r:adult.data:1", fields)
    assert caught.value.code == code


def test_source_qualified_row_ids_round_trip_and_reject_malformed_input():
    text = make_row_id("uci-adult-2", "adult.data", 7)
    assert text == "uci-adult-2:adult.data:7"
    parsed = parse_row_id(text)
    assert (parsed.release, parsed.source_file, parsed.line) == ("uci-adult-2", "adult.data", 7)
    # The same line number in the other file is a different row.
    assert make_row_id("uci-adult-2", "adult.test", 7) != text
    for bad in (
        lambda: make_row_id("uci:adult-2", "adult.data", 7),
        lambda: make_row_id("", "adult.data", 7),
        lambda: make_row_id("rel", "adult.csv", 7),
        lambda: make_row_id("rel", "adult.data", 0),
        lambda: make_row_id("rel", "adult.data", True),
        lambda: make_row_id("rel", "adult.data", 1.0),
        lambda: parse_row_id("rel:adult.data:007"),
        lambda: parse_row_id("rel:adult.data"),
        lambda: record_from_raw_fields("not-a-qualified-id", fabricated_fields()),
    ):
        with pytest.raises(AdultAdapterError) as caught:
            bad()
        assert caught.value.code == "ROW_ID"


def test_adapter_import_pulls_in_no_agent_api_experiments_or_bank_module():
    code = (
        "import sys\n"
        "import shiftguard.adult_adapter\n"
        "import shiftguard.adult_adapter.features, shiftguard.adult_adapter.missingness, "
        "shiftguard.adult_adapter.grouping\n"
        "bad = sorted(m for m in sys.modules if m.split('.')[:2] in "
        "(['shiftguard','agent'], ['shiftguard','api'], ['shiftguard','experiments'], "
        "['shiftguard','datasets']) and m != 'shiftguard.datasets' and m != 'shiftguard.datasets.adult')\n"
        "print(repr(bad))\n"
        "assert not bad, bad\n"
    )
    completed = subprocess.run(
        [sys.executable, "-B", "-c", code], cwd=REPO_ROOT, capture_output=True, text=True, timeout=120
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout.strip() == "[]"
