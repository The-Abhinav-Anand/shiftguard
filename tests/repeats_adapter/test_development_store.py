"""Gate 8 precondition 4: the restartable, digest-referencing development coordinate store.

Fabricated Bank-shaped rows only (see development_fixtures); nothing under var/datasets or any
real file is read, and tests never write under the real repository var/.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import os
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

import pytest

from development_fixtures import (
    Lab,
    development_standin_binding,
    development_standin_dataset,
    fabricated_bank_dataset,
    pin_verified_bank,
)
from shiftguard.repeats import development_store as store_module
from shiftguard.repeats.completion import (
    IDEMPOTENT_REUSE,
    INSERT,
    CompletionRecord,
    Conflict,
    build_completion,
    serialize_artifact,
)
from shiftguard.repeats.development_adapter import validate_coordinate_result
from shiftguard.repeats.development_store import (
    COMPACT_CELL_RECORD_VERSION,
    COORDINATE_RECORD_VERSION,
    SEAMS,
    DevelopmentCoordinateStore,
    StoredCoordinate,
    decode_coordinate,
    encode_coordinate,
)
from shiftguard.repeats.models import (
    INNER_IDS,
    OUTER_SEEDS,
    PAIRED_CELL_RECORD_VERSION,
    PRIMARY_BUDGET,
    PRIMARY_SCENARIOS,
    PRIMARY_SOURCE_METHOD,
    PRIMARY_TARGET_METHOD,
    RepeatContractError,
)
from shiftguard.repeats.synthetic_store import SyntheticRepeatStore


OUTER, INNER = OUTER_SEEDS[0], INNER_IDS[0]
SCOPE = {
    "scenarios": PRIMARY_SCENARIOS, "budgets": (0, PRIMARY_BUDGET),
    "methods": (PRIMARY_SOURCE_METHOD, PRIMARY_TARGET_METHOD),
}


class SimulatedCrash(BaseException):
    pass


def _code(call) -> RepeatContractError:
    with pytest.raises(RepeatContractError) as caught:
        call()
    return caught.value


@pytest.fixture(scope="module")
def lab() -> Lab:
    return Lab()


@pytest.fixture(scope="module")
def result(lab):
    return lab.run(OUTER, INNER, **SCOPE)


@pytest.fixture(scope="module")
def encoded(lab, result):
    return encode_coordinate(lab.plan, result)


@pytest.fixture(scope="module")
def _dev_lab_cache() -> Lab:
    dataset = development_standin_dataset()
    with pytest.MonkeyPatch.context() as patch:
        pin_verified_bank(patch, development_standin_binding(dataset))
        return Lab(dataset, development=True)


@pytest.fixture
def dev_lab(_dev_lab_cache, monkeypatch) -> Lab:
    pin_verified_bank(monkeypatch, _dev_lab_cache.binding)
    return _dev_lab_cache


def _sums_cell(result):
    return next(cell for cell in result.pair_cells if cell.paired_loss_sum_by_group is not None)


def _other_content(result):
    """Same repeat, valid coordinate, one paired sum changed."""
    cells = list(result.pair_cells)
    cell = _sums_cell(result)
    sums = list(cell.paired_loss_sum_by_group)
    position = next(i for i, value in enumerate(sums) if value != 0.0)
    sums[position] = sums[position] / 2
    index = cells.index(cell)
    cells[index] = dataclasses.replace(cell, paired_loss_sum_by_group=tuple(sums))
    return dataclasses.replace(result, pair_cells=tuple(cells))


@pytest.fixture
def outside_repo(monkeypatch):
    """A stand-in repository outside verification/, so its path never trips the forbidden-name check."""
    base = Path(tempfile.mkdtemp(prefix="gate8-store-test-"))
    repo = base / "repo"
    monkeypatch.setattr(store_module, "REPO_ROOT", repo)
    monkeypatch.setattr(store_module, "PRIVATE_VAR_ROOT", repo / "var")
    yield repo
    shutil.rmtree(base, ignore_errors=True)


def _forge(root, result, mutate):
    """Replace the stored artifact by self-consistent bytes (hashes, canonical form) of mutated content."""
    marker = root / "completions" / f"{result.repeat_id}.json"
    old = json.loads(marker.read_bytes())
    blob = root / "artifacts" / f"{old['artifact_byte_hashes'][0][1]}.json"
    value = json.loads(blob.read_bytes())
    mutate(value)
    forged = serialize_artifact(value)
    sha = hashlib.sha256(forged).hexdigest()
    (root / "artifacts" / f"{sha}.json").write_bytes(forged)
    marker.write_bytes(marker.read_bytes().replace(
        old["artifact_byte_hashes"][0][1].encode(), sha.encode()).replace(
        old["logical_content_sha256"].encode(), hashlib.sha256(forged[:-1]).hexdigest().encode()))


def _sum_pattern(cell):
    return [struct.pack("<d", value) for value in cell.paired_loss_sum_by_group]


# ---------------------------------------------------------------- encoding and decoding

def test_round_trip_is_exact_and_validates(lab, result, encoded):
    record, artifact = encoded
    decoded = decode_coordinate(lab.plan, artifact)
    assert decoded == result
    assert [c.digest for c in decoded.contexts] == [c.digest for c in result.contexts]
    assert [c.context.digest for c in decoded.pair_cells] == [c.context.digest for c in result.pair_cells]
    assert [type(c.paired_loss_sum_by_group) for c in decoded.pair_cells] == [
        type(c.paired_loss_sum_by_group) for c in result.pair_cells]
    validate_coordinate_result(lab.plan, decoded)
    assert record.repeat_id == result.repeat_id and record.terminal_status == "completed"
    assert result.pair_cells and result.validated_pairs


def test_encoding_is_deterministic_ascii_with_one_trailing_lf(lab, result, encoded):
    again = encode_coordinate(lab.plan, result)
    assert again == encoded
    artifact = encoded[1]
    assert artifact.endswith(b"\n") and not artifact.endswith(b"\n\n")
    artifact.decode("ascii")
    envelope = json.loads(artifact)
    assert envelope["record_version"] == COORDINATE_RECORD_VERSION
    assert envelope["plan_digest"] == lab.plan.plan_digest
    assert envelope["roles_digest"] == lab.plan.roles(OUTER).digest
    assert {cell["record_version"] for cell in envelope["content"]["pair_cells"]} == {
        COMPACT_CELL_RECORD_VERSION}
    assert COMPACT_CELL_RECORD_VERSION != PAIRED_CELL_RECORD_VERSION


def test_compact_artifact_holds_no_plan_owned_copy(lab, result, encoded):
    artifact = encoded[1]
    manifest = lab.plan.roles(OUTER)
    for name in (b"evaluation_ids", b"group_map", b"group_ids", b"n_by_group", b"acquired_prefix"):
        assert name not in artifact
    for row_id in (manifest.evaluation_ids[0], manifest.evaluation_ids[-1]):
        assert row_id.encode("ascii") not in artifact
    for group in lab.plan.group_universe[:3]:
        assert group.encode("ascii") not in artifact
    # The acquisition order is per coordinate but stored as positions, not row ids.
    assert manifest.target_pool_ids[0].encode("ascii") not in artifact
    # No label or row-level value is ever part of the content.
    assert set(json.loads(artifact)["content"]) == {
        "outer_seed", "inner_id", "seed_map_digest", "execution_tier", "claim_scope",
        "acquisition_order_index", "contexts", "conditions", "pair_cells", "validated_pairs"}


def test_compact_artifact_is_substantially_smaller_than_the_naive_serialization(lab, result, encoded):
    naive = serialize_artifact({
        "cells": [c.to_canonical() for c in result.pair_cells],
        "conditions": [c.to_canonical() for c in result.conditions],
        "contexts": [c.to_canonical() for c in result.contexts],
    })
    compact = encoded[1]
    assert len(naive) > 4 * len(compact), (len(naive), len(compact))


@pytest.mark.parametrize("field", [
    "evaluation_ids", "group_map", "dataset", "release", "protocol", "seed_map",
    "source_binding", "acquired_prefix", "outer",
])
def test_encoding_refuses_a_tampered_plan_owned_context_field(lab, result, field):
    context = result.contexts[0]
    if field == "evaluation_ids":
        ids = tuple(reversed(context.evaluation_ids))
        changed = dataclasses.replace(
            context, evaluation_ids=ids,
            group_map=tuple(zip(ids, (g for _, g in reversed(context.group_map)))))
    elif field == "group_map":
        pairs = list(context.group_map)
        other = next(i for i, (_, g) in enumerate(pairs) if g != pairs[0][1])
        pairs[0], pairs[other] = (pairs[0][0], pairs[other][1]), (pairs[other][0], pairs[0][1])
        changed = dataclasses.replace(context, group_map=tuple(pairs))
    elif field == "acquired_prefix":
        # The prefix is rebuilt from the acquisition order, so a reordered order disagrees with it.
        order = list(result.acquisition_order)
        order[0], order[1] = order[1], order[0]
        tampered = dataclasses.replace(result, acquisition_order=tuple(order))
        error = _code(lambda: encode_coordinate(lab.plan, tampered))
        assert error.code == "PLAN_OWNED_MISMATCH"
        return
    elif field == "outer":
        changed = dataclasses.replace(context, outer=OUTER_SEEDS[1])
    else:
        replacement = "f" * 64 if field in ("seed_map", "source_binding") else "tampered-" + field
        changed = dataclasses.replace(context, **{field: replacement})
    tampered = dataclasses.replace(result, contexts=(changed, *result.contexts[1:]))
    error = _code(lambda: encode_coordinate(lab.plan, tampered))
    assert error.code == "PLAN_OWNED_MISMATCH"


def test_encoding_refuses_a_tampered_acquisition_order_and_identity(lab, result):
    short = dataclasses.replace(result, acquisition_order=result.acquisition_order[:-1])
    assert _code(lambda: encode_coordinate(lab.plan, short)).code == "PLAN_OWNED_MISMATCH"
    other_repeat = lab.plan.repeat(OUTER, INNER_IDS[1]).repeat_id
    wrong_id = dataclasses.replace(result, repeat_id=other_repeat)
    assert _code(lambda: encode_coordinate(lab.plan, wrong_id)).code == "PLAN_OWNED_MISMATCH"
    other_seeds = lab.plan.repeat(OUTER, INNER_IDS[1]).seed_map
    wrong_seeds = dataclasses.replace(result, seed_map=other_seeds)
    assert _code(lambda: encode_coordinate(lab.plan, wrong_seeds)).code == "PLAN_OWNED_MISMATCH"


def test_encoding_refuses_tampered_cell_groups_and_counts(lab, result):
    cell = _sums_cell(result)
    index = result.pair_cells.index(cell)

    def with_cell(**changes):
        cells = list(result.pair_cells)
        cells[index] = dataclasses.replace(cell, **changes)
        return dataclasses.replace(result, pair_cells=tuple(cells))

    groups = cell.group_ids
    renamed = with_cell(group_ids=(*groups[:-1], groups[-1] + "0"))
    assert _code(lambda: encode_coordinate(lab.plan, renamed)).detail == "cell.group_ids"
    counts = list(cell.n_by_group)
    other = next(i for i, value in enumerate(counts) if value != counts[0])
    counts[0], counts[other] = counts[other], counts[0]
    zeros = tuple(0.0 for _ in counts)  # keeps the per-group bounds valid under the swap
    swapped = with_cell(n_by_group=tuple(counts), paired_loss_sum_by_group=zeros)
    assert _code(lambda: encode_coordinate(lab.plan, swapped)).detail == "cell.n_by_group"


def test_encoding_refuses_a_cell_whose_context_is_not_a_coordinate_context(lab, result):
    cell = _sums_cell(result)
    index = result.pair_cells.index(cell)
    foreign = dataclasses.replace(cell.context, test_mask="e" * 64)
    cells = list(result.pair_cells)
    cells[index] = dataclasses.replace(cell, context=foreign)
    tampered = dataclasses.replace(result, pair_cells=tuple(cells))
    assert _code(lambda: encode_coordinate(lab.plan, tampered)).code in ("PAIR_BINDING", "PLAN_OWNED_MISMATCH")


def test_decoding_is_strict_about_the_stored_bytes(lab, encoded):
    artifact = encoded[1]
    envelope = json.loads(artifact)

    def decode(mutate):
        value = json.loads(artifact)
        mutate(value)
        return _code(lambda: decode_coordinate(lab.plan, serialize_artifact(value))).code

    assert decode(lambda v: v.update(plan_digest="0" * 64)) == "ARTIFACT_PLAN_MISMATCH"
    assert decode(lambda v: v.update(roles_digest="0" * 64)) == "ARTIFACT_PLAN_MISMATCH"
    assert decode(lambda v: v.update(record_version="gate8-dev-coordinate-v0")) == "RECORD_VERSION"
    assert decode(lambda v: v.update(extra=1)) == "COMPACT_RECORD_FIELDS"
    assert decode(lambda v: v["content"].update(extra=1)) == "COMPACT_RECORD_FIELDS"
    assert decode(lambda v: v["content"]["acquisition_order_index"].__setitem__(
        0, v["content"]["acquisition_order_index"][1])) == "COMPACT_ORDER"
    assert decode(lambda v: v["content"]["pair_cells"][0].update(
        record_version=PAIRED_CELL_RECORD_VERSION)) == "RECORD_VERSION"
    assert decode(lambda v: v["content"]["pair_cells"][0].update(context=10_000)) == "COMPACT_REFERENCE"
    cell = next(c for c in envelope["content"]["pair_cells"] if c["sums"])
    position = envelope["content"]["pair_cells"].index(cell)
    assert decode(lambda v: v["content"]["pair_cells"][position]["sums"]["nonzero_index"].reverse()) \
        == "COMPACT_SUMS"
    # Valid JSON that is not the canonical serialization is refused too.
    pretty = json.dumps(envelope, indent=1).encode("ascii") + b"\n"
    assert _code(lambda: decode_coordinate(lab.plan, pretty)).code == "ARTIFACT_NOT_CANONICAL"


def test_stored_coordinate_repr_is_short_and_shows_no_sums(lab, result, tmp_path):
    store = DevelopmentCoordinateStore(tmp_path / "store", lab.plan)
    store.commit(result, attempt_id="attempt-1")
    stored = store.load(result.repeat_id)
    assert isinstance(stored, StoredCoordinate)
    text = repr(stored)
    assert len(text) < 1000
    assert "artifact=" not in text and "result=" not in text and "paired_loss_sum" not in text
    assert "cells" not in text and "nonzero" not in text


def test_sparse_sums_preserve_the_sign_of_zero_bit_for_bit(lab, result):
    cell = _sums_cell(result)
    sums = list(cell.paired_loss_sum_by_group)
    positives = [i for i, value in enumerate(sums) if value == 0.0 and math.copysign(1.0, value) > 0]
    assert len(positives) >= 2
    sums[positives[0]] = -0.0  # a stored negative zero; the other zeros stay exact +0.0
    cells = list(result.pair_cells)
    cells[result.pair_cells.index(cell)] = dataclasses.replace(
        cell, paired_loss_sum_by_group=tuple(sums))
    signed = dataclasses.replace(result, pair_cells=tuple(cells))
    record, artifact = encode_coordinate(lab.plan, signed)
    decoded = decode_coordinate(lab.plan, artifact)
    after = decoded.pair_cells[result.pair_cells.index(cell)]
    assert _sum_pattern(after) == [struct.pack("<d", value) for value in sums]
    assert math.copysign(1.0, after.paired_loss_sum_by_group[positives[0]]) < 0
    assert math.copysign(1.0, after.paired_loss_sum_by_group[positives[1]]) > 0
    # And it differs from the all-positive encoding, so the sign is really stored.
    assert artifact != encode_coordinate(lab.plan, result)[1]


def test_decoder_refuses_noncanonical_sparse_values(lab, encoded):
    artifact = encoded[1]
    envelope = json.loads(artifact)
    position = next(i for i, c in enumerate(envelope["content"]["pair_cells"]) if c["sums"])

    def decode(mutate):
        value = json.loads(artifact)
        mutate(value["content"]["pair_cells"][position]["sums"])
        return _code(lambda: decode_coordinate(lab.plan, serialize_artifact(value))).code

    assert decode(lambda sums: sums["nonzero_values"].__setitem__(0, 0.0)) == "COMPACT_SUMS"
    assert decode(lambda sums: sums["nonzero_values"].__setitem__(0, 1)) == "COMPACT_SUMS"
    assert decode(lambda sums: sums["nonzero_values"].__setitem__(0, True)) == "COMPACT_SUMS"


def test_rebuilt_plan_owned_values_are_digest_bound(lab, encoded):
    artifact = encoded[1]
    envelope = json.loads(artifact)
    assert len(envelope["plan_owned_digest"]) == 64
    value = json.loads(artifact)
    value["plan_owned_digest"] = "0" * 64
    assert _code(lambda: decode_coordinate(lab.plan, serialize_artifact(value))).code == "ARTIFACT_PLAN_MISMATCH"
    del value["plan_owned_digest"]
    assert _code(lambda: decode_coordinate(lab.plan, serialize_artifact(value))).code == "COMPACT_RECORD_FIELDS"


def test_malformed_results_raise_typed_codes(lab, result):
    bad = dataclasses.replace(result, pair_cells=None)
    assert isinstance(_code(lambda: encode_coordinate(lab.plan, bad)), RepeatContractError)
    bad = dataclasses.replace(result, contexts=5)
    assert isinstance(_code(lambda: encode_coordinate(lab.plan, bad)), RepeatContractError)
    assert _code(lambda: encode_coordinate(lab.plan, object())).code == "COORDINATE_SCHEMA"


# ---------------------------------------------------------------- restart

def test_restart_skips_only_a_verified_completed_coordinate(lab, result, tmp_path):
    root = tmp_path / "store"
    first = DevelopmentCoordinateStore(root, lab.plan)
    outcome = first.commit(result, attempt_id="attempt-1")
    assert outcome.decision is INSERT and first.orphaned_staging() == ()
    reopened = DevelopmentCoordinateStore(root, lab.plan)
    assert reopened.completed_repeat_ids() == (result.repeat_id,)
    stored = reopened.load(result.repeat_id)
    assert stored.result == result and stored.record == outcome.record
    assert reopened.load(lab.plan.repeat(OUTER, INNER_IDS[1]).repeat_id) is None
    assert reopened.corrupt_completion_ids() == ()


def _committed_store(lab, result, tmp_path):
    root = tmp_path / "store"
    DevelopmentCoordinateStore(root, lab.plan).commit(result, attempt_id="attempt-1")
    return root


def _assert_corrupt(lab, root, result):
    store = DevelopmentCoordinateStore(root, lab.plan)
    assert _code(lambda: store.load(result.repeat_id)).code == "CORRUPT_COMPLETION"
    assert store.completed_repeat_ids() == ()
    assert store.corrupt_completion_ids() == (result.repeat_id,)


def test_a_flipped_artifact_byte_is_corrupt_never_absent_or_completed(lab, result, tmp_path):
    root = _committed_store(lab, result, tmp_path)
    blob = next((root / "artifacts").iterdir())
    data = bytearray(blob.read_bytes())
    data[len(data) // 2] ^= 0x01
    blob.write_bytes(bytes(data))
    _assert_corrupt(lab, root, result)


def test_a_truncated_artifact_is_corrupt(lab, result, tmp_path):
    root = _committed_store(lab, result, tmp_path)
    blob = next((root / "artifacts").iterdir())
    blob.write_bytes(blob.read_bytes()[:-40])
    _assert_corrupt(lab, root, result)


def test_a_missing_artifact_is_corrupt(lab, result, tmp_path):
    root = _committed_store(lab, result, tmp_path)
    next((root / "artifacts").iterdir()).unlink()
    _assert_corrupt(lab, root, result)


@pytest.mark.parametrize("damage", ["empty", "truncated", "garbage", "other_record"])
def test_a_damaged_completion_marker_is_corrupt(lab, result, tmp_path, damage):
    root = _committed_store(lab, result, tmp_path)
    marker = root / "completions" / f"{result.repeat_id}.json"
    raw = marker.read_bytes()
    marker.write_bytes({
        "empty": b"", "truncated": raw[: len(raw) // 2], "garbage": b"\xff\xfe not json",
        "other_record": raw.replace(result.repeat_id.encode(), b"0" * 64),
    }[damage])
    _assert_corrupt(lab, root, result)


def test_a_self_consistent_artifact_that_fails_validation_is_corrupt(lab, result, tmp_path):
    root = _committed_store(lab, result, tmp_path)
    # Hashes, canonical form and plan digests all hold; only the joined validation can object.
    _forge(root, result, lambda v: v["content"]["acquisition_order_index"].reverse())
    _assert_corrupt(lab, root, result)


def test_commit_over_a_deep_corrupt_existing_record_is_corruption_not_a_conflict(lab, result, tmp_path):
    root = _committed_store(lab, result, tmp_path)
    _forge(root, result, lambda v: v["content"]["validated_pairs"][0].update(row_count=1))
    store = DevelopmentCoordinateStore(root, lab.plan)
    # Light checks pass, so a light-only decision would call this a content conflict.
    assert store._read(result.repeat_id, deep=False) is not None
    assert _code(lambda: store.commit(result, attempt_id="attempt-2")).code == "CORRUPT_COMPLETION"
    assert [a.outcome for a in store.attempts(result.repeat_id)] == ["INSERT"]
    assert _code(lambda: store.commit(
        _other_content(result), attempt_id="attempt-3")).code == "CORRUPT_COMPLETION"
    assert store.completed_repeat_ids() == ()


def test_a_real_lost_publication_race_over_a_corrupt_record_is_corruption(lab, result, tmp_path):
    donor = _committed_store(lab, result, tmp_path / "donor-parent")
    _forge(donor, result, lambda v: v["content"]["validated_pairs"][0].update(row_count=1))
    root = tmp_path / "raced"

    def plant(seam):
        # Another writer publishes a light-valid, deep-invalid record right before our commit point.
        if seam == "before_commit":
            for sub in ("artifacts", "completions"):
                for path in (donor / sub).iterdir():
                    if sub == "completions" or not (root / sub / path.name).exists():
                        (root / sub / path.name).write_bytes(path.read_bytes())

    store = DevelopmentCoordinateStore(root, lab.plan, fault=plant)
    assert _code(lambda: store.commit(result, attempt_id="attempt-1")).code == "CORRUPT_COMPLETION"
    assert store.completed_repeat_ids() == () and store.attempts(result.repeat_id) == ()


def _link(link, target):
    try:
        if os.name == "nt":
            made = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
            if made.returncode != 0:
                raise OSError("mklink /J failed")
        else:
            os.symlink(target, link, target_is_directory=True)
    except OSError:
        pytest.skip("cannot create a junction or symlink here")


def _unlink(link):
    if link.exists():
        os.rmdir(link) if os.name == "nt" else link.unlink()


def test_a_store_subdirectory_that_is_a_link_outside_the_root_is_refused(lab, result, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    half = tmp_path / "half"
    half.mkdir()
    link = half / "artifacts"
    _link(link, outside)
    try:
        assert _code(lambda: DevelopmentCoordinateStore(half, lab.plan)).code == "STORE_IDENTITY"
        assert list(outside.iterdir()) == []
        # The same holds for an established store whose directory is later replaced by a link.
        root = tmp_path / "store"
        DevelopmentCoordinateStore(root, lab.plan)
        (root / "completions").rmdir()
        _link(root / "completions", outside)
        try:
            assert _code(lambda: DevelopmentCoordinateStore(root, lab.plan)).code == "STORE_IDENTITY"
            assert list(outside.iterdir()) == []
        finally:
            _unlink(root / "completions")
    finally:
        _unlink(link)


def test_the_store_marker_is_published_atomically(lab, tmp_path):
    root = tmp_path / "store"

    def crash(seam):
        if seam == store_module.MARKER_SEAM:
            raise SimulatedCrash(seam)

    with pytest.raises(SimulatedCrash):
        DevelopmentCoordinateStore(root, lab.plan, fault=crash)
    assert not (root / "STORE.json").exists()  # never empty or partial
    reopened = DevelopmentCoordinateStore(root, lab.plan)
    assert (root / "STORE.json").is_file() and len(reopened.orphaned_staging()) == 1
    assert reopened.completed_repeat_ids() == ()
    # A damaged marker that exists anyway is still refused, never adopted.
    for damage in (b"", b'{"schema":"gate8-dev'):
        (root / "STORE.json").write_bytes(damage)
        assert _code(lambda: DevelopmentCoordinateStore(root, lab.plan)).code == "STORE_IDENTITY"
    empty_marker = tmp_path / "empty-marker"
    empty_marker.mkdir()
    (empty_marker / "STORE.json").write_bytes(b"")
    assert _code(lambda: DevelopmentCoordinateStore(empty_marker, lab.plan)).code == "STORE_IDENTITY"


@pytest.mark.parametrize("seam", SEAMS)
def test_a_crash_at_every_seam_leaves_no_completion_or_a_fully_verified_one(lab, result, tmp_path, seam):
    root = tmp_path / "store"

    def fault(name):
        if name == seam:
            raise SimulatedCrash(name)

    crashing = DevelopmentCoordinateStore(root, lab.plan, fault=fault)
    with pytest.raises(SimulatedCrash):
        crashing.commit(result, attempt_id="attempt-1")
    reopened = DevelopmentCoordinateStore(root, lab.plan)
    completed = reopened.completed_repeat_ids()
    if seam == "after_commit":
        assert completed == (result.repeat_id,)
        assert reopened.load(result.repeat_id).result == result
    else:
        assert completed == () and reopened.load(result.repeat_id) is None
    assert reopened.corrupt_completion_ids() == ()
    if seam in ("after_stage_artifact", "before_commit"):
        assert reopened.orphaned_staging() != ()  # reported, never removed
    reopened.record_failed_attempt(result.repeat_id, "crashed-1", "simulated_crash")
    assert reopened.completed_repeat_ids() == completed  # a failed attempt is never a completion
    # Retrying after the crash always ends in exactly one verified completion.
    retry = reopened.commit(result, attempt_id="attempt-2")
    assert retry.decision in (INSERT, IDEMPOTENT_REUSE)
    assert reopened.completed_repeat_ids() == (result.repeat_id,)
    assert reopened.load(result.repeat_id).result == result


# ---------------------------------------------------------------- identity and immutability

def test_a_store_opened_with_another_plan_refuses(lab, result, tmp_path):
    root = _committed_store(lab, result, tmp_path)
    dataset = fabricated_bank_dataset(row_count=2300)
    other = Lab(dataset)
    assert other.plan.plan_digest != lab.plan.plan_digest
    assert _code(lambda: DevelopmentCoordinateStore(root, other.plan)).code == "STORE_IDENTITY"
    # Neither a foreign non-empty directory nor a synthetic store root is adopted.
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (foreign / "x").write_text("x")
    assert _code(lambda: DevelopmentCoordinateStore(foreign, lab.plan)).code == "STORE_IDENTITY"
    synthetic_root = tmp_path / "synthetic"
    SyntheticRepeatStore(synthetic_root)
    assert _code(lambda: DevelopmentCoordinateStore(synthetic_root, lab.plan)).code == "STORE_IDENTITY"


def test_identical_recommit_reuses_and_different_content_conflicts_without_overwrite(lab, result, tmp_path):
    root = tmp_path / "store"
    store = DevelopmentCoordinateStore(root, lab.plan)
    first = store.commit(result, attempt_id="attempt-1")
    blob = next((root / "artifacts").iterdir())
    marker = root / "completions" / f"{result.repeat_id}.json"
    before = (blob.read_bytes(), marker.read_bytes())
    again = store.commit(result, attempt_id="attempt-2")
    assert again.decision is IDEMPOTENT_REUSE and again.record == first.record
    assert _code(lambda: store.commit(result, attempt_id="attempt-2")).code == "DUPLICATE_ATTEMPT"
    conflicting = store.commit(_other_content(result), attempt_id="attempt-3")
    assert isinstance(conflicting.decision, Conflict)
    assert conflicting.decision.reason == "logical_content_differs"
    assert conflicting.record == first.record
    assert (blob.read_bytes(), marker.read_bytes()) == before
    assert [p.name for p in (root / "artifacts").iterdir()] == [blob.name]
    assert [a.outcome for a in store.attempts(result.repeat_id)] == [
        "INSERT", "IDEMPOTENT_REUSE", "CONFLICT"]
    assert store.load(result.repeat_id).result == result
    assert store.orphaned_staging() == ()


def test_inventory_is_one_deep_scan_for_completed_failed_and_corrupt(lab, result, tmp_path, monkeypatch):
    second = lab.run(OUTER, INNER_IDS[1], **SCOPE)
    root = tmp_path / "store"
    store = DevelopmentCoordinateStore(root, lab.plan)
    store.commit(result, attempt_id="attempt-1")
    store.commit(second, attempt_id="attempt-1")
    blob = root / "artifacts" / f"{store.load(second.repeat_id).record.artifact_byte_hashes[0][1]}.json"
    blob.write_bytes(blob.read_bytes()[:-9])
    loads = []
    original = store.load
    monkeypatch.setattr(store, "load", lambda repeat_id: loads.append(repeat_id) or original(repeat_id))
    found = store.inventory()
    assert (found.completed, found.failed, found.corrupt) == (
        (result.repeat_id,), (), (second.repeat_id,))
    assert sorted(loads) == sorted([result.repeat_id, second.repeat_id])  # each record verified once
    monkeypatch.undo()
    assert store.completed_repeat_ids() == found.completed
    assert store.corrupt_completion_ids() == found.corrupt
    assert store.terminal_failure_ids() == found.failed


def test_a_half_created_root_is_adopted_but_a_foreign_one_is_not(lab, result, tmp_path):
    root = tmp_path / "half"
    for name in ("staging", "artifacts", "completions"):
        (root / name).mkdir(parents=True)
    store = DevelopmentCoordinateStore(root, lab.plan)
    assert (root / "STORE.json").is_file() and (root / "attempts").is_dir()
    assert store.commit(result, attempt_id="attempt-1").decision is INSERT
    stray = tmp_path / "stray"
    (stray / "artifacts").mkdir(parents=True)
    (stray / "artifacts" / "x.json").write_text("x")
    assert _code(lambda: DevelopmentCoordinateStore(stray, lab.plan)).code == "STORE_IDENTITY"
    other = tmp_path / "other"
    (other / "elsewhere").mkdir(parents=True)
    assert _code(lambda: DevelopmentCoordinateStore(other, lab.plan)).code == "STORE_IDENTITY"


# ---------------------------------------------------------------- evaluator-private placement

def test_a_development_plan_refuses_the_default_root_outside_var(dev_lab, tmp_path):
    error = _code(lambda: DevelopmentCoordinateStore(tmp_path / "store", dev_lab.plan))
    assert error.code == "PRIVATE_ROOT_REQUIRED"
    assert not (tmp_path / "store").exists()
    repo = store_module.REPO_ROOT
    assert store_module.PRIVATE_VAR_ROOT == repo / "var"
    assert (repo / ".gitignore").is_file() and (repo / "shiftguard" / "repeats").is_dir()
    lines = [line.strip() for line in (repo / ".gitignore").read_text(encoding="utf-8").splitlines()]
    assert "var/" in lines
    assert store_module.PRIVATE_SUBTREE == "gate8-private"


def test_the_private_root_guard_for_development_plans(dev_lab, outside_repo, tmp_path):
    repo = outside_repo
    private = repo / "var" / "gate8-private"

    def code(path):
        return _code(lambda: DevelopmentCoordinateStore(path, dev_lab.plan)).code

    assert code(tmp_path / "store") == "PRIVATE_ROOT_REQUIRED"
    assert code(repo / "verification" / "store") == "PRIVATE_ROOT_REQUIRED"
    assert code(repo / "var") == "PRIVATE_ROOT_REQUIRED"
    assert code(repo / "var" / "store") == "PRIVATE_ROOT_REQUIRED"  # outside the dedicated subtree
    assert code(repo / "var" / "artifacts" / "store") == "PRIVATE_ROOT_REQUIRED"
    assert code(private) == "PRIVATE_ROOT_REQUIRED"
    assert code(repo / "var2" / "gate8-private" / "store") == "PRIVATE_ROOT_REQUIRED"
    assert code(private / ".." / "store") == "PRIVATE_ROOT_REQUIRED"
    assert code(private / "verification" / "store") == "PRIVATE_ROOT_FORBIDDEN"
    assert code(private / "Verification" / "x" / "store") == "PRIVATE_ROOT_FORBIDDEN"
    assert not (repo / "var").exists()  # refusals create nothing
    assert DevelopmentCoordinateStore(private / "store", dev_lab.plan).completed_repeat_ids() == ()


def test_a_repository_inside_a_verification_directory_is_forbidden(dev_lab, monkeypatch):
    base = Path(tempfile.mkdtemp(prefix="gate8-store-test-"))
    try:
        repo = base / "Verification" / "repo"
        monkeypatch.setattr(store_module, "REPO_ROOT", repo)
        monkeypatch.setattr(store_module, "PRIVATE_VAR_ROOT", repo / "var")
        error = _code(lambda: DevelopmentCoordinateStore(
            repo / "var" / "gate8-private" / "store", dev_lab.plan))
        assert error.code == "PRIVATE_ROOT_FORBIDDEN"
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_the_guard_accepts_the_real_private_subtree_and_creates_nothing(dev_lab):
    private = store_module.REPO_ROOT / "var" / "gate8-private"
    target = private / "unit-test-store"
    before = (private.exists(), target.exists())
    store_module.require_private_root(target, dev_lab.plan)
    assert (private.exists(), target.exists()) == before
    assert not target.exists()


def test_a_private_var_root_that_is_not_the_repository_var_is_refused(dev_lab, outside_repo, monkeypatch):
    monkeypatch.setattr(store_module, "PRIVATE_VAR_ROOT", outside_repo / "elsewhere")
    path = outside_repo / "elsewhere" / "gate8-private" / "store"
    assert _code(lambda: DevelopmentCoordinateStore(path, dev_lab.plan)).code == "PRIVATE_ROOT_REQUIRED"


def test_a_link_inside_the_private_root_pointing_outside_is_refused(dev_lab, outside_repo, tmp_path):
    private = outside_repo / "var" / "gate8-private"
    private.mkdir(parents=True)
    target = Path(tempfile.mkdtemp(prefix="gate8-store-target-"))
    link = private / "link"
    try:
        try:
            if os.name == "nt":
                made = subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
                if made.returncode != 0:
                    raise OSError("mklink /J failed")
            else:
                os.symlink(target, link, target_is_directory=True)
        except OSError:
            pytest.skip("cannot create a junction or symlink here")
        error = _code(lambda: DevelopmentCoordinateStore(link / "store", dev_lab.plan))
        assert error.code == "PRIVATE_ROOT_REQUIRED"
        assert not (target / "store").exists()
    finally:
        if link.exists():
            if os.name == "nt":
                os.rmdir(link)
            else:
                link.unlink()
        shutil.rmtree(target, ignore_errors=True)


def test_a_development_coordinate_round_trips_and_restarts_in_a_private_root(dev_lab, lab, outside_repo):
    result = dev_lab.run(OUTER, INNER, **SCOPE)
    root = outside_repo / "var" / "gate8-private" / "dev-store"
    committed = DevelopmentCoordinateStore(root, dev_lab.plan).commit(result, attempt_id="attempt-1")
    assert committed.decision is INSERT
    reopened = DevelopmentCoordinateStore(root, dev_lab.plan)
    assert reopened.completed_repeat_ids() == (result.repeat_id,)
    stored = reopened.load(result.repeat_id)
    assert stored.result == result
    assert [c.digest for c in stored.result.contexts] == [c.digest for c in result.contexts]
    assert json.loads((root / "STORE.json").read_bytes())["evaluator_private"] is True
    # A development plan cannot be reopened as a store of the synthetic lab's plan.
    assert _code(lambda: DevelopmentCoordinateStore(root, lab.plan)).code == "STORE_IDENTITY"


# ---------------------------------------------------------------- synthetic gate regression

def test_the_synthetic_store_and_completion_still_refuse_development_content(dev_lab, tmp_path):
    plan = dev_lab.plan
    assert _code(lambda: build_completion(
        plan, plan.repeats[0].repeat_id, {"synthetic": True}, "completed")).code == "SYNTHETIC_ONLY"
    record, artifact = encode_coordinate(plan, dev_lab.run(OUTER, INNER, **SCOPE))
    # Re-name the artifact so the synthetic store's own hash and canonical checks pass.
    record = CompletionRecord(
        record.repeat_id, record.logical_content_sha256,
        (("completion.json", record.artifact_byte_hashes[0][1]),), "completed")
    synthetic = SyntheticRepeatStore(tmp_path / "synthetic")
    # Self-consistent hashes and canonical bytes; the synthetic envelope check rejects it.
    assert _code(lambda: synthetic.commit(record, artifact, attempt_id="attempt-1")).code == "ARTIFACT_ENVELOPE"
    assert synthetic.completed_repeat_ids() == ()
