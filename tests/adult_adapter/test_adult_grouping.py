"""Gate 9 Adult adapter: label-blind group keys, grouped allocation and quarantine.

All rows are fabricated in the test; no label, Adult file or manifest is used.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import random

import pytest

from shiftguard.adult_adapter.features import (
    ADULT_FEATURE_CONTRACT,
    AdultAdapterError,
    AdultRecord,
    make_row_id,
    record_from_raw_fields,
)
from shiftguard.adult_adapter.grouping import (
    GROUP_ORDER_VERSION,
    MINIMUM_POOL_ROWS,
    ROLES,
    allocate_grouped_roles,
    group_key,
    quarantine_test_connected,
)
from shiftguard.datasets import adult as parser


@pytest.fixture(autouse=True)
def forbid_real_adult_paths(monkeypatch):
    def tripwire(name):
        def raiser(*_args, **_kwargs):
            raise AssertionError(f"adapter test reached {name}")
        return raiser

    for name in ("clean_adult_rows", "make_adult_role_splits", "acquire_adult_train_only", "execute_adult_confirmatory"):
        monkeypatch.setattr(parser, name, tripwire(name))


def fields(i: int, **overrides: str) -> dict[str, str]:
    values = {
        "age": str(20 + i % 50), "workclass": "Private", "fnlwgt": str(100000 + i),
        "education-num": "9", "marital-status": "Never-married", "occupation": "Sales",
        "relationship": "Not-in-family", "race": "White", "sex": "Male",
        "capital-gain": "0", "capital-loss": "0", "hours-per-week": "40",
        "native-country": "United-States",
    }
    values.update(overrides)
    return values


def rec(line: int, source: str = "adult.data", _key: int | None = None, **overrides: str) -> AdultRecord:
    """Row at ``line``; rows built with the same ``_key`` and overrides share a feature vector."""
    return record_from_raw_fields(
        make_row_id("rel", source, line), fields(line if _key is None else _key, **overrides)
    )


def corpus(n_unique: int = 1700, duplicate_sizes: tuple[int, ...] = (40, 25, 12, 5, 5, 3, 2, 2)) -> tuple[AdultRecord, ...]:
    """Unique rows plus duplicate groups (same features, different line ids)."""
    rows = [rec(i + 1) for i in range(n_unique)]
    line = n_unique
    for g, size in enumerate(duplicate_sizes):
        shared = fields(900000 + g)  # one feature vector per duplicate group
        for _ in range(size):
            line += 1
            rows.append(record_from_raw_fields(make_row_id("rel", "adult.data", line), shared))
    return tuple(rows)


def role_of(result, row_id):
    for role in ROLES:
        if row_id in result.role(role).row_ids:
            return role
    raise AssertionError("row not allocated")


# ---------------------------------------------------------------- group keys

def test_group_key_follows_the_documented_canonical_json_formula():
    r = rec(1, workclass="?")
    tokens = list(r.tokens)
    assert tokens[1] is None
    payload = json.dumps(
        ["gate8-feature-group-v1", ADULT_FEATURE_CONTRACT.schema_digest, tokens],
        sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False,
    )
    assert group_key(r) == hashlib.sha256(payload.encode("ascii")).hexdigest()
    assert len(group_key(r)) == 64


def test_missing_marker_and_literal_values_make_distinct_keys():
    base = group_key(rec(1, workclass="?"))
    for literal in ("Unknown", "None", "null", "NA", "unknown"):
        assert group_key(rec(1, workclass=literal)) != base
    assert group_key(rec(1, workclass="Private")) != base
    # Exact spelling is part of the key: no numeric or case normalisation.
    assert group_key(rec(1, age="39")) != group_key(rec(1, age="39.0"))
    assert group_key(rec(1, workclass="private")) != group_key(rec(1, workclass="Private"))
    # Naturally missing in different positions is not the same group.
    assert group_key(rec(1, workclass="?")) != group_key(rec(1, occupation="?"))


def test_group_key_ignores_row_id_source_file_and_release_but_not_features():
    a = record_from_raw_fields(make_row_id("rel-a", "adult.data", 1), fields(5))
    b = record_from_raw_fields(make_row_id("rel-b", "adult.test", 99), fields(5))
    assert group_key(a) == group_key(b)  # comparable across files under one schema
    assert group_key(a) != group_key(record_from_raw_fields(make_row_id("rel-a", "adult.data", 1), fields(6)))


def test_group_key_binds_the_schema_digest():
    r = rec(1)
    other = dataclasses.replace(ADULT_FEATURE_CONTRACT, natural_missing_token="NA")
    assert group_key(r, other) != group_key(r)


def test_records_have_no_label_slot():
    assert {f.name for f in dataclasses.fields(AdultRecord)} == {"row_id", "tokens"}


# ---------------------------------------------------------------- allocation

def test_allocation_reports_achieved_counts_and_targets_exactly():
    rows = corpus()
    result = allocate_grouped_roles(rows, split_seed=7)
    n = len(rows)
    assert result.status == "OK" and result.unsupported_roles == ()
    assert result.row_count == n and result.group_count == len({group_key(r) for r in rows})
    assert sum(result.role(r).row_count for r in ROLES) == n
    assert sum(result.role(r).group_count for r in ROLES) == result.group_count
    for role, fraction in zip(ROLES, (0.6875, 0.1875, 0.125), strict=True):
        slot = result.role(role)
        assert slot.target_fraction == fraction
        assert slot.target_rows == n * fraction
        assert slot.row_count == len(slot.row_ids)
        assert slot.achieved_fraction == slot.row_count / n
        assert slot.deviation_rows == slot.row_count - n * fraction
        # Each overshoot is below one group size, so any shortfall is below two group sizes.
        assert abs(slot.deviation_rows) < 2 * result.largest_group_rows
    assert result.largest_group_rows == 40
    assert len(result.allocation_digest) == 64


def test_allocation_is_deterministic_and_input_order_invariant():
    rows = corpus()
    first = allocate_grouped_roles(rows, split_seed=11)
    again = allocate_grouped_roles(rows, split_seed=11)
    assert first == again
    shuffled = list(rows)
    random.Random(2).shuffle(shuffled)
    permuted = allocate_grouped_roles(tuple(shuffled), split_seed=11)
    assert permuted == first
    assert permuted.allocation_digest == first.allocation_digest
    # The split seed matters, and only through the group order.
    other = allocate_grouped_roles(rows, split_seed=12)
    assert other.allocation_digest != first.allocation_digest


def test_group_order_uses_the_documented_hash_and_largest_deficit_rule():
    # Three tiny groups of one row each, hand-checked: N=3, targets 2.0625 / 0.5625 / 0.375.
    rows = tuple(rec(i) for i in (1, 2, 3))
    seed = 3
    keys = sorted((group_key(r) for r in rows), key=lambda g: (
        hashlib.sha256(json.dumps([GROUP_ORDER_VERSION, seed, g], sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest(), g))
    by_key = {group_key(r): r.row_id for r in rows}
    result = allocate_grouped_roles(rows, split_seed=seed, minimum_pool_rows=0)
    # First group: deficits 2.0625 > 0.5625 > 0.375 -> train. Second: 1.0625 > 0.5625 -> train.
    # Third: train deficit 0.0625, source_cal 0.5625, target_pool 0.375 -> source_cal.
    assert result.role("train").row_ids == (by_key[keys[0]], by_key[keys[1]])
    assert result.role("source_cal").row_ids == (by_key[keys[2]],)
    assert result.role("target_pool").row_ids == ()
    assert result.unsupported_roles == ("target_pool",)


def test_whole_groups_stay_together_and_members_are_in_row_id_order():
    rows = corpus()
    result = allocate_grouped_roles(rows, split_seed=5)
    by_group: dict[str, set[str]] = {}
    for r in rows:
        by_group.setdefault(group_key(r), set()).add(role_of(result, r.row_id))
    assert all(len(roles) == 1 for roles in by_group.values())
    # Every row appears exactly once.
    allocated = [i for role in ROLES for i in result.role(role).row_ids]
    assert len(allocated) == len(set(allocated)) == len(rows)
    # Within one group the members are appended in numeric line order (10 after 9, not before).
    members = [r.row_id for r in rows if group_key(r) == group_key(rec(1, _key=900000))]
    assert len(members) == 40
    slot = result.role(role_of(result, members[0])).row_ids
    positions = [slot.index(m) for m in members]
    assert positions == sorted(positions) and positions == list(range(positions[0], positions[0] + 40))
    lines = [int(m.rsplit(":", 1)[1]) for m in (slot[p] for p in positions)]
    assert lines == sorted(lines)


def test_unsupported_when_the_pool_is_below_the_minimum():
    rows = tuple(rec(i + 1) for i in range(1000))  # pool target 125 < 200
    result = allocate_grouped_roles(rows, split_seed=1)
    assert MINIMUM_POOL_ROWS == 200
    assert result.status == "UNSUPPORTED_ROLE"
    assert "target_pool" in result.unsupported_roles
    assert result.role("target_pool").row_count < 200
    assert sum(result.role(r).row_count for r in ROLES) == 1000  # counts still reported, nothing dropped
    with pytest.raises(AdultAdapterError) as caught:
        result.require_supported()
    assert caught.value.code == "UNSUPPORTED_ROLE"


def test_unsupported_when_a_role_is_empty_and_for_empty_input():
    one_group = tuple(record_from_raw_fields(make_row_id("rel", "adult.data", i), fields(1)) for i in range(1, 501))
    result = allocate_grouped_roles(one_group, split_seed=1)
    assert result.status == "UNSUPPORTED_ROLE"
    assert set(result.unsupported_roles) == {"source_cal", "target_pool"}
    assert result.role("train").row_count == 500
    empty = allocate_grouped_roles((), split_seed=1)
    assert empty.status == "UNSUPPORTED_ROLE" and empty.row_count == 0


def test_a_supported_allocation_does_not_raise():
    allocate_grouped_roles(corpus(), split_seed=1).require_supported()


def test_allocation_input_validation():
    rows = corpus(300, ())
    for bad_seed in (True, 1.0, "1", None):
        with pytest.raises(AdultAdapterError) as caught:
            allocate_grouped_roles(rows, split_seed=bad_seed)
        assert caught.value.code == "SEED_TYPE"
    with pytest.raises(AdultAdapterError) as caught:
        allocate_grouped_roles(rows + (rows[0],), split_seed=1)
    assert caught.value.code == "DUPLICATE_ROW_ID"
    with pytest.raises(AdultAdapterError) as caught:
        allocate_grouped_roles(rows + (rec(99999, source="adult.test"),), split_seed=1)
    assert caught.value.code == "NON_DEVELOPMENT_ROW"
    with pytest.raises(AdultAdapterError) as caught:
        allocate_grouped_roles(list(rows), split_seed=1)  # type: ignore[arg-type]
    assert caught.value.code == "IMMUTABLE_TUPLE"


def test_group_members_are_appended_in_numeric_line_order_not_text_order():
    shared = fields(1)
    rows = tuple(record_from_raw_fields(make_row_id("rel", "adult.data", n), shared) for n in (100, 9, 10))
    result = allocate_grouped_roles(rows, split_seed=1, minimum_pool_rows=0)
    assert result.role("train").row_ids == tuple(f"rel:adult.data:{n}" for n in (9, 10, 100))


# ---------------------------------------------------------------- quarantine

def test_quarantine_removes_every_member_of_every_declared_group():
    rows = corpus()
    big = group_key(rec(1, _key=900000))      # 40 members
    small = group_key(rec(1, _key=900007))    # 2 members
    single = group_key(rows[10])                     # unique row
    absent = hashlib.sha256(b"absent").hexdigest()
    result = quarantine_test_connected(rows, {big, small, single, absent})
    expected = {r.row_id for r in rows if group_key(r) in {big, small, single}}
    assert len(expected) == 43
    assert set(result.quarantined_row_ids) == expected
    assert not expected & {r.row_id for r in result.retained}
    assert all(group_key(r) not in {big, small, single} for r in result.retained)
    assert result.original_row_count == len(rows)
    assert result.quarantined_row_count == 43 and result.retained_row_count == len(rows) - 43
    assert result.quarantined_group_ids == tuple(sorted({big, small, single}))
    assert result.declared_group_count == 4 and result.declared_groups_absent_count == 1
    assert result.original_group_count - result.retained_group_count == 3
    assert result.reason == "test_connected_exact_feature_group"
    # Reported ids are in numeric source-qualified order.
    lines = [int(i.rsplit(":", 1)[1]) for i in result.quarantined_row_ids]
    assert lines == sorted(lines)


def test_quarantine_precedes_allocation_and_no_quarantined_row_is_allocated():
    rows = corpus()
    declared = {group_key(rec(1, _key=900000 + g)) for g in range(4)}
    q = quarantine_test_connected(rows, declared)
    result = allocate_grouped_roles(q.retained, split_seed=4)
    allocated = {i for role in ROLES for i in result.role(role).row_ids}
    assert not allocated & set(q.quarantined_row_ids)
    assert allocated == {r.row_id for r in q.retained}
    assert result.row_count == len(rows) - len(q.quarantined_row_ids)


def test_quarantine_input_order_does_not_matter_and_empty_declaration_is_a_noop():
    rows = corpus(200, (6, 3))
    declared = {group_key(rows[0]), group_key(rows[-1])}
    shuffled = list(rows)
    random.Random(1).shuffle(shuffled)
    a = quarantine_test_connected(rows, declared)
    b = quarantine_test_connected(tuple(shuffled), declared)
    assert a.quarantined_row_ids == b.quarantined_row_ids
    assert {r.row_id for r in a.retained} == {r.row_id for r in b.retained}
    nothing = quarantine_test_connected(rows, set())
    assert nothing.quarantined_row_ids == () and nothing.retained_row_count == len(rows)


def test_quarantine_input_validation():
    rows = corpus(50, ())
    with pytest.raises(AdultAdapterError) as caught:
        quarantine_test_connected(rows, {"not-a-digest"})
    assert caught.value.code == "DIGEST"
    with pytest.raises(AdultAdapterError) as caught:
        quarantine_test_connected(rows, [group_key(rows[0])])  # type: ignore[arg-type]
    assert caught.value.code == "GROUP_KEY_SET"
    with pytest.raises(AdultAdapterError) as caught:
        quarantine_test_connected(rows + (rec(7000, source="adult.test"),), {group_key(rows[0])})
    assert caught.value.code == "NON_DEVELOPMENT_ROW"
    with pytest.raises(AdultAdapterError) as caught:
        quarantine_test_connected(rows + (rows[0],), {group_key(rows[0])})
    assert caught.value.code == "DUPLICATE_ROW_ID"
