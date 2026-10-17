"""Restartable, digest-referencing filesystem store for development (Bank) repeat coordinates.

Gate 8 precondition 4. Not a migration, not a public API and not a workflow engine. A
coordinate is persisted as a compact artifact: everything the plan already owns (the
evaluation ids and group map of every pair context, each cell's group universe and counts,
dataset/release/protocol/seed-map/source-binding fields, acquired prefixes) is referenced by
the plan and the role digests and rebuilt from the plan on reopen, never copied. Encoding
refuses any result whose plan-owned field differs from the plan-derived value, and then
proves exactness by decoding its own bytes, so decoding is exact by construction.

Bytes are staged and fsynced first; a coordinate counts as completed only once its record
is published by one atomic, exclusive hard link under its full repeat ID. Nothing is ever
overwritten; interrupted staging files and failed attempts are kept. Reopen re-verifies the
byte hash, the canonical serialization, the plan and roles digests, decodes against the plan
and runs ``validate_coordinate_result``; any failure is ``CORRUPT_COMPLETION``, never absence.

Evaluator-private boundary: paired group sums are outcome-equivalent. For any plan whose
source is not ``synthetic_fabricated`` the store root must resolve inside the repository's
gitignored ``var/`` and outside ``verification/``. Labels and raw rows are never stored:
the result is already the label-free reduction plus paired sums.

``synthetic_store`` and ``completion`` stay synthetic-only and are not touched here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
from typing import Any, Callable, Mapping
from uuid import uuid4

from shiftguard.repeats.completion import (
    INSERT,
    CompletionDecision,
    CompletionRecord,
    Conflict,
    completion_action,
    serialize_artifact,
)
from shiftguard.repeats.development_adapter import (
    CoordinateResult,
    validate_coordinate_result,
)
from shiftguard.repeats.models import (
    SYNTHETIC_EXPOSURE,
    PairContext,
    PairedGroupLossCell,
    RepeatContractError,
    RepeatKey,
    RepeatPlan,
    TerminalCondition,
    ValidatedPair,
    canonical_digest,
    canonical_json,
    declared_repeat,
    digest_field,
    identifier,
)
from shiftguard.repeats.planning import (
    ensure_planned,
    pair_context_for,
    plan_owned_mismatch,
)


STORE_SCHEMA = "gate8-dev-repeat-store-v1"
COORDINATE_RECORD_VERSION = "gate8-dev-coordinate-v1"
# Deliberately distinct from models.PAIRED_CELL_RECORD_VERSION: this cell carries no context,
# group universe or counts, and its sums are sparse.
COMPACT_CELL_RECORD_VERSION = "gate8-dev-compact-cell-v1"
COMPACT_CONTEXT_RECORD_VERSION = "gate8-dev-compact-context-v1"
COMPACT_PAIR_RECORD_VERSION = "gate8-dev-compact-pair-v1"
ARTIFACT_NAME = "coordinate.json"
TERMINAL_STATUS = "completed"
# Named persistence seams, in order, where a fault hook may stop the process.
MARKER_SEAM = "before_marker_publish"
SEAMS = (
    "before_stage", "after_stage_artifact", "after_publish_artifact",
    "before_commit", "after_commit",
)
# Evaluator-private placement. Module-level so tests can point it at a temporary tree.
REPO_ROOT = Path(__file__).resolve().parents[2]
PRIVATE_VAR_ROOT = REPO_ROOT / "var"
# The app's recovery loop deletes stale directories elsewhere under var/ (artifacts, .staging),
# so development stores live only in this dedicated subtree.
PRIVATE_SUBTREE = "gate8-private"
FORBIDDEN_ROOT_NAME = "verification"
PLAN_OWNED_DIGEST_VERSION = "gate8-dev-plan-owned-v1"

_CONTEXT_FIELDS = ("predictor", "scenario", "budget", "test_mask", "pool_mask", "predictor_id")
_ENVELOPE_KEYS = {
    "content", "plan_digest", "plan_owned_digest", "record_version", "repeat_id",
    "roles_digest", "source_binding_digest", "terminal_status",
}
_STORE_DIRECTORIES = ("staging", "artifacts", "completions", "attempts")
_CONTENT_KEYS = {
    "acquisition_order_index", "claim_scope", "conditions", "contexts", "execution_tier",
    "inner_id", "outer_seed", "pair_cells", "seed_map_digest", "validated_pairs",
}
_CELL_KEYS = {
    "context", "qualification", "reasons", "record_version", "source_condition_id",
    "source_resolution_counts", "source_resolved_method", "sums", "target_condition_id",
    "target_resolution_counts", "target_resolved_method",
}
_ATTEMPT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
_ATTEMPT_FILE = re.compile(r"(\d{6})-([A-Za-z0-9][A-Za-z0-9_-]{0,63})\.json")
_REPEAT_FILE = re.compile(r"([0-9a-f]{64})\.json")


@dataclass(frozen=True)
class StoredCoordinate:
    record: CompletionRecord
    # Neither is shown in a repr: the artifact is large and the result holds paired sums.
    artifact: bytes = field(repr=False)
    result: CoordinateResult | None = field(repr=False)  # decoded and validated; None for a light read


@dataclass(frozen=True)
class StoreInventory:
    """One deep scan: coordinates that fully re-verify, terminal failures and damaged records."""

    completed: tuple[str, ...]
    failed: tuple[str, ...]
    corrupt: tuple[str, ...]


@dataclass(frozen=True)
class CommitResult:
    """``record`` is what the store holds afterwards, also when the commit conflicted."""

    decision: CompletionDecision | Conflict
    record: CompletionRecord


@dataclass(frozen=True)
class AttemptRecord:
    attempt_id: str
    outcome: str
    reason: str | None
    recorded_at_utc: str
    audit_json: str


# ------------------------------------------------------------------ compact encoding

def _is_positive_zero(value: float) -> bool:
    return value == 0.0 and math.copysign(1.0, value) > 0


def _strict_index(value: Any, bound: int, code: str) -> int:
    if type(value) is not int or not 0 <= value < bound:
        raise RepeatContractError(code, "index")
    return value


def _owned(detail: str) -> RepeatContractError:
    return RepeatContractError("PLAN_OWNED_MISMATCH", detail)


def _check_identity(plan: RepeatPlan, result: CoordinateResult) -> RepeatKey:
    if type(result) is not CoordinateResult or type(result.key) is not RepeatKey:
        raise RepeatContractError("COORDINATE_SCHEMA", "result")
    key = result.key
    declared_repeat(key.outer_seed, key.inner_id)
    planned = plan.repeat(key.outer_seed, key.inner_id)
    if result.repeat_id != planned.repeat_id:
        raise _owned("repeat_id")
    if result.seed_map != planned.seed_map:
        raise _owned("seed_map")
    return key


def _check_plan_owned(plan: RepeatPlan, result: CoordinateResult, key: RepeatKey) -> dict[str, int]:
    """Typed-code mapping of every omitted field; returns the pool index.

    Meant for validated input. On input that failed validation it may itself fail on malformed
    values; the caller then keeps the validation error.
    """
    manifest = plan.roles(key.outer_seed)
    pool_index = {row_id: index for index, row_id in enumerate(manifest.target_pool_ids)}
    order = result.acquisition_order
    if len(order) != len(pool_index) or any(
        row_id not in pool_index for row_id in order
    ) or len(set(order)) != len(order):
        raise _owned("acquisition_order")
    order_digest = canonical_digest(["gate8-acquisition-order-v1", list(order)])
    for context in result.contexts:
        if (context.outer, context.inner) != (key.outer_seed, key.inner_id):
            raise _owned("outer/inner")
        names = list(plan_owned_mismatch(plan, context))
        if context.acquired_prefix != order[:context.budget]:
            names.append("acquired_prefix_not_order_prefix")
        if context.acquisition_order != order_digest:
            names.append("acquisition_order_digest")
        if names:
            raise _owned("context." + ",".join(names))
    universe, counts = plan.group_universe, plan.group_counts(key.outer_seed)
    for cell in result.pair_cells:
        if cell.group_ids != universe:
            raise _owned("cell.group_ids")
        if cell.n_by_group != counts:
            raise _owned("cell.n_by_group")
    return pool_index


def _plan_owned_digest(plan: RepeatPlan, outer: int, contexts: tuple[PairContext, ...]) -> str:
    """Binds the rebuilt plan-owned values, so bytes cannot silently decode against changed rebuild code."""
    return canonical_digest([
        PLAN_OWNED_DIGEST_VERSION, list(plan.group_universe), list(plan.group_counts(outer)),
        [context.digest for context in contexts],
    ])


def _sum_bits(result: CoordinateResult) -> list[bytes | None]:
    """Float bit patterns of every cell's sums: == cannot tell -0.0 from +0.0, these can."""
    return [
        None if cell.paired_loss_sum_by_group is None
        else b"".join(struct.pack("<d", value) for value in cell.paired_loss_sum_by_group)
        for cell in result.pair_cells
    ]


def _encode_cell(cell: PairedGroupLossCell, context_index: int) -> dict[str, Any]:
    sums = cell.paired_loss_sum_by_group
    stored = None
    if sums is not None:
        # Absent groups hold an exact +0.0; every other value, -0.0 included, is stored.
        index = [i for i, value in enumerate(sums) if not _is_positive_zero(value)]
        stored = {"nonzero_index": index, "nonzero_values": [sums[i] for i in index]}
    return {
        "record_version": COMPACT_CELL_RECORD_VERSION,
        "context": context_index,
        "target_condition_id": cell.target_condition_id,
        "source_condition_id": cell.source_condition_id,
        "sums": stored,
        "qualification": cell.qualification,
        "reasons": list(cell.reasons),
        "target_resolved_method": cell.target_resolved_method,
        "source_resolved_method": cell.source_resolved_method,
        "target_resolution_counts": [list(pair) for pair in cell.target_resolution_counts],
        "source_resolution_counts": [list(pair) for pair in cell.source_resolution_counts],
    }


def _encode_content(result: CoordinateResult, pool_index: dict[str, int]) -> dict[str, Any]:
    context_slots: dict[tuple[str, str, int], int] = {}
    for index, context in enumerate(result.contexts):
        context_slots.setdefault((context.predictor, context.scenario, context.budget), index)

    def reference(context: PairContext) -> int:
        index = context_slots.get((context.predictor, context.scenario, context.budget))
        if index is None or result.contexts[index] != context:
            raise RepeatContractError("PAIR_BINDING", "pair context is not a coordinate context")
        return index

    return {
        "outer_seed": result.key.outer_seed,
        "inner_id": result.key.inner_id,
        "seed_map_digest": result.seed_map.digest,
        "execution_tier": result.execution_tier,
        "claim_scope": result.claim_scope,
        "acquisition_order_index": [pool_index[row_id] for row_id in result.acquisition_order],
        "contexts": {
            "record_version": COMPACT_CONTEXT_RECORD_VERSION,
            "fields": list(_CONTEXT_FIELDS),
            "rows": [[getattr(context, name) for name in _CONTEXT_FIELDS] for context in result.contexts],
        },
        "conditions": [condition.to_canonical() for condition in result.conditions],
        "pair_cells": [_encode_cell(cell, reference(cell.context)) for cell in result.pair_cells],
        "validated_pairs": [{
            "record_version": COMPACT_PAIR_RECORD_VERSION,
            "context": reference(pair.context),
            "row_count": pair.row_count,
            "target_digest": pair.target_digest,
            "source_digest": pair.source_digest,
        } for pair in result.validated_pairs],
    }


def _record_for(repeat_id: str, artifact: bytes) -> CompletionRecord:
    return CompletionRecord(
        repeat_id=repeat_id,
        logical_content_sha256=hashlib.sha256(artifact[:-1]).hexdigest(),
        artifact_byte_hashes=((ARTIFACT_NAME, hashlib.sha256(artifact).hexdigest()),),
        terminal_status=TERMINAL_STATUS,
    )


def encode_coordinate(plan: RepeatPlan, result: CoordinateResult) -> tuple[CompletionRecord, bytes]:
    """Compact, canonical, deterministic bytes of one validated coordinate, and their record."""
    ensure_planned(plan)
    key = _check_identity(plan, result)
    try:
        validate_coordinate_result(plan, result)
    except RepeatContractError as error:
        # Prefer the precise plan-owned code when the failure is one; never mask the typed error.
        try:
            _check_plan_owned(plan, result, key)
        except RepeatContractError as owned:
            if owned.code == "PLAN_OWNED_MISMATCH":
                raise
        except Exception:  # noqa: BLE001  malformed input: the validation error is the answer
            pass
        raise error
    pool_index = _check_plan_owned(plan, result, key)
    artifact = serialize_artifact({
        "record_version": COORDINATE_RECORD_VERSION,
        "plan_digest": plan.plan_digest,
        "roles_digest": plan.roles(key.outer_seed).digest,
        "source_binding_digest": plan.binding.digest,
        "plan_owned_digest": _plan_owned_digest(plan, key.outer_seed, result.contexts),
        "repeat_id": result.repeat_id,
        "terminal_status": TERMINAL_STATUS,
        "content": _encode_content(result, pool_index),
    })
    # Exactness by construction: the bytes must decode to precisely what was encoded, including
    # the sign of every zero sum (== alone cannot tell -0.0 from +0.0).
    decoded = decode_coordinate(plan, artifact)
    if decoded != result or _sum_bits(decoded) != _sum_bits(result):
        raise RepeatContractError("COMPACT_NOT_EXACT", result.repeat_id)
    return _record_for(result.repeat_id, artifact), artifact


def _fields(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise RepeatContractError("COMPACT_RECORD_FIELDS", label)
    return value


def _versioned(value: Any, version: str, label: str) -> None:
    if not isinstance(value, dict) or value.get("record_version") != version:
        raise RepeatContractError("RECORD_VERSION", label)


def _decode_cell(
    value: Any, contexts: tuple[PairContext, ...],
    universe: tuple[str, ...], counts: tuple[int, ...],
) -> PairedGroupLossCell:
    _versioned(value, COMPACT_CELL_RECORD_VERSION, "compact cell")
    value = _fields(value, _CELL_KEYS, "compact cell")
    sums = None
    if value["sums"] is not None:
        stored = _fields(value["sums"], {"nonzero_index", "nonzero_values"}, "compact sums")
        index, values = stored["nonzero_index"], stored["nonzero_values"]
        if type(index) is not list or type(values) is not list or len(index) != len(values):
            raise RepeatContractError("COMPACT_SUMS", "shape")
        dense = [0.0] * len(universe)
        previous = -1
        for position, item in zip(index, values):
            _strict_index(position, len(universe), "COMPACT_SUMS")
            if position <= previous or type(item) is not float or _is_positive_zero(item):
                raise RepeatContractError("COMPACT_SUMS", "not canonical")
            dense[position] = item
            previous = position
        sums = tuple(dense)
    try:
        target_counts = tuple(tuple(pair) for pair in value["target_resolution_counts"])
        source_counts = tuple(tuple(pair) for pair in value["source_resolution_counts"])
        reasons = tuple(value["reasons"])
    except TypeError:
        raise RepeatContractError("RECORD_FIELDS", "compact cell") from None
    return PairedGroupLossCell(
        context=contexts[_strict_index(value["context"], len(contexts), "COMPACT_REFERENCE")],
        target_condition_id=value["target_condition_id"],
        source_condition_id=value["source_condition_id"],
        group_ids=universe,
        n_by_group=counts,
        paired_loss_sum_by_group=sums,
        qualification=value["qualification"],
        reasons=reasons,
        target_resolved_method=value["target_resolved_method"],
        source_resolved_method=value["source_resolved_method"],
        target_resolution_counts=target_counts,
        source_resolution_counts=source_counts,
    )


def _decode_content(
    plan: RepeatPlan, repeat_id: str, content: Any, plan_owned_digest: str,
) -> CoordinateResult:
    content = _fields(content, _CONTENT_KEYS, "content")
    outer, inner = content["outer_seed"], content["inner_id"]
    if type(outer) is not int or type(inner) is not int:
        raise RepeatContractError("COMPACT_RECORD_FIELDS", "key")
    declared_repeat(outer, inner)
    key = RepeatKey(outer, inner)
    planned = plan.repeat(outer, inner)
    if planned.repeat_id != repeat_id or content["seed_map_digest"] != planned.seed_map.digest:
        raise RepeatContractError("COORDINATE_IDENTITY", f"{outer}/{inner}")
    manifest = plan.roles(outer)
    pool = manifest.target_pool_ids
    positions = content["acquisition_order_index"]
    if type(positions) is not list or len(positions) != len(pool):
        raise RepeatContractError("COMPACT_ORDER", "length")
    for position in positions:
        _strict_index(position, len(pool), "COMPACT_ORDER")
    if len(set(positions)) != len(pool):
        raise RepeatContractError("COMPACT_ORDER", "not a permutation of the pool")
    order = tuple(pool[position] for position in positions)
    order_digest = canonical_digest(["gate8-acquisition-order-v1", list(order)])

    stored_contexts = content["contexts"]
    _versioned(stored_contexts, COMPACT_CONTEXT_RECORD_VERSION, "compact contexts")
    stored_contexts = _fields(
        stored_contexts, {"fields", "record_version", "rows"}, "compact contexts")
    if stored_contexts["fields"] != list(_CONTEXT_FIELDS) or type(stored_contexts["rows"]) is not list:
        raise RepeatContractError("COMPACT_RECORD_FIELDS", "context fields")
    contexts = []
    for row in stored_contexts["rows"]:
        if type(row) is not list or len(row) != len(_CONTEXT_FIELDS):
            raise RepeatContractError("COMPACT_RECORD_FIELDS", "context row")
        fields = dict(zip(_CONTEXT_FIELDS, row))
        budget = fields.pop("budget")
        contexts.append(pair_context_for(
            plan, key, fields.pop("predictor"), fields.pop("scenario"), budget,
            acquisition_order=order_digest, acquired_prefix=order[:budget]
            if type(budget) is int and budget >= 0 else (), **fields))
    contexts = tuple(contexts)
    if plan_owned_digest != _plan_owned_digest(plan, outer, contexts):
        raise RepeatContractError("ARTIFACT_PLAN_MISMATCH", "plan-owned values")

    try:
        conditions = tuple(TerminalCondition.from_canonical(item) for item in content["conditions"])
    except TypeError:
        raise RepeatContractError("RECORD_FIELDS", "conditions") from None
    universe, counts = plan.group_universe, plan.group_counts(outer)
    if type(content["pair_cells"]) is not list or type(content["validated_pairs"]) is not list:
        raise RepeatContractError("COMPACT_RECORD_FIELDS", "pair lists")
    cells = tuple(
        _decode_cell(item, contexts, universe, counts) for item in content["pair_cells"])
    pairs = []
    for item in content["validated_pairs"]:
        _versioned(item, COMPACT_PAIR_RECORD_VERSION, "compact pair")
        item = _fields(item, {
            "context", "record_version", "row_count", "source_digest", "target_digest"},
            "compact pair")
        pairs.append(ValidatedPair(
            context=contexts[_strict_index(item["context"], len(contexts), "COMPACT_REFERENCE")],
            row_count=item["row_count"], target_digest=item["target_digest"],
            source_digest=item["source_digest"]))
    return CoordinateResult(
        key=key, repeat_id=repeat_id, seed_map=planned.seed_map,
        execution_tier=content["execution_tier"], claim_scope=content["claim_scope"],
        acquisition_order=order, contexts=contexts, conditions=conditions,
        validated_pairs=tuple(pairs), pair_cells=cells,
    )


def _parse_envelope(plan: RepeatPlan, artifact: bytes) -> dict[str, Any]:
    """Canonical-bytes and binding checks shared by the light and the deep reopen."""
    try:
        envelope = json.loads(artifact.decode("ascii"))
    except (UnicodeDecodeError, ValueError):
        raise RepeatContractError("ARTIFACT_NOT_CANONICAL") from None
    if serialize_artifact(envelope) != artifact:
        raise RepeatContractError("ARTIFACT_NOT_CANONICAL")
    _versioned(envelope, COORDINATE_RECORD_VERSION, "coordinate")
    envelope = _fields(envelope, _ENVELOPE_KEYS, "coordinate")
    if envelope["terminal_status"] != TERMINAL_STATUS:
        raise RepeatContractError("ARTIFACT_ENVELOPE", "terminal_status")
    if (
        envelope["plan_digest"] != plan.plan_digest
        or envelope["source_binding_digest"] != plan.binding.digest
    ):
        raise RepeatContractError("ARTIFACT_PLAN_MISMATCH", "plan or source binding")
    return envelope


def _decode_envelope(plan: RepeatPlan, envelope: dict[str, Any]) -> CoordinateResult:
    repeat_id = digest_field(envelope["repeat_id"], "repeat_id")
    content = envelope["content"]
    if not isinstance(content, dict) or type(content.get("outer_seed")) is not int:
        raise RepeatContractError("COMPACT_RECORD_FIELDS", "content")
    if envelope["roles_digest"] != plan.roles(content["outer_seed"]).digest:
        raise RepeatContractError("ARTIFACT_PLAN_MISMATCH", "roles digest")
    return _decode_content(plan, repeat_id, content, envelope["plan_owned_digest"])


def decode_coordinate(plan: RepeatPlan, artifact: bytes) -> CoordinateResult:
    """Rebuild the coordinate from its bytes and the plan; every constructor re-validates."""
    if type(plan) is not RepeatPlan or type(artifact) is not bytes:
        raise RepeatContractError("REPEAT_SCHEMA", "plan/artifact")
    return _decode_envelope(plan, _parse_envelope(plan, artifact))


def verify_coordinate_artifact(
    plan: RepeatPlan, record: CompletionRecord, artifact: bytes, *, deep: bool = True,
) -> CoordinateResult | None:
    """Bytes against their record; with ``deep`` also decode against the plan and validate."""
    if type(record) is not CompletionRecord or type(artifact) is not bytes:
        raise RepeatContractError("REPEAT_SCHEMA", "record/artifact")
    if record.artifact_byte_hashes != ((ARTIFACT_NAME, hashlib.sha256(artifact).hexdigest()),):
        raise RepeatContractError("ARTIFACT_HASH_MISMATCH", record.repeat_id)
    if record.logical_content_sha256 != hashlib.sha256(artifact[:-1]).hexdigest():
        raise RepeatContractError("LOGICAL_HASH_MISMATCH", record.repeat_id)
    if record.terminal_status != TERMINAL_STATUS:
        raise RepeatContractError("TERMINAL_STATUS", record.terminal_status)
    envelope = _parse_envelope(plan, artifact)
    if envelope["repeat_id"] != record.repeat_id:
        raise RepeatContractError("ARTIFACT_ENVELOPE", record.repeat_id)
    if not deep:
        return None
    result = _decode_envelope(plan, envelope)
    validate_coordinate_result(plan, result)
    return result


# ------------------------------------------------------------------ evaluator-private placement

def require_private_root(root: Path, plan: RepeatPlan) -> None:
    """Non-synthetic sums may only live under var/gate8-private, never in evidence or recovery areas."""
    if plan.binding.exposure_status == SYNTHETIC_EXPOSURE:
        return
    resolved = Path(root).resolve()
    repo_root = Path(REPO_ROOT).resolve()
    var_root = Path(PRIVATE_VAR_ROOT).resolve()
    private = var_root / PRIVATE_SUBTREE
    if var_root != repo_root / "var":
        raise RepeatContractError("PRIVATE_ROOT_REQUIRED", "private var root is not the repository var/")
    if not resolved.is_relative_to(private) or resolved == private:
        raise RepeatContractError(
            "PRIVATE_ROOT_REQUIRED", f"store root must be inside the repository var/{PRIVATE_SUBTREE}")
    if FORBIDDEN_ROOT_NAME in {part.lower() for part in resolved.parts}:
        raise RepeatContractError("PRIVATE_ROOT_FORBIDDEN", "store root must not be inside verification/")


def _marker_bytes(plan: RepeatPlan) -> bytes:
    return (canonical_json({
        "schema": STORE_SCHEMA,
        "plan_digest": plan.plan_digest,
        "source_binding_digest": plan.binding.digest,
        "evaluator_private": plan.binding.exposure_status != SYNTHETIC_EXPOSURE,
    }) + "\n").encode("ascii")


def _record_marker_bytes(record: CompletionRecord) -> bytes:
    return (canonical_json({
        "schema": STORE_SCHEMA,
        "repeat_id": record.repeat_id,
        "logical_content_sha256": record.logical_content_sha256,
        "artifact_byte_hashes": [list(pair) for pair in record.artifact_byte_hashes],
        "terminal_status": record.terminal_status,
    }) + "\n").encode("ascii")


class DevelopmentCoordinateStore:
    def __init__(
        self, root: Path, plan: RepeatPlan, *, fault: Callable[[str], None] | None = None,
    ) -> None:
        ensure_planned(plan)  # also refuses an unauthorized source binding
        require_private_root(root, plan)
        self.root = Path(root)
        self.plan = plan
        self._fault_hook = fault
        expected = _marker_bytes(plan)
        marker = self.root / "STORE.json"
        if self.root.exists():
            if not self.root.is_dir():
                raise RepeatContractError("STORE_IDENTITY", str(self.root))
            children = list(self.root.iterdir())
            marked = marker.is_file() and marker.read_bytes() == expected
            # A root that crashed before its marker holds only the known directories; only
            # staging may hold (orphaned) files.
            half_created = not marker.exists() and all(
                child.is_dir() and child.name in _STORE_DIRECTORIES
                and (child.name == "staging" or not any(child.iterdir()))
                for child in children
            )
            if children and not (marked or half_created):
                raise RepeatContractError("STORE_IDENTITY", str(self.root))
            # Nothing may be redirected elsewhere by a junction or symlink inside the root.
            real = self.root.resolve()
            for name in (*_STORE_DIRECTORIES, "STORE.json"):
                if (self.root / name).exists() and (self.root / name).resolve() != real / name:
                    raise RepeatContractError("STORE_IDENTITY", f"{name} resolves outside the store root")
        self._staging = self.root / "staging"
        self._artifacts = self.root / "artifacts"
        self._completions = self.root / "completions"
        self._attempts = self.root / "attempts"
        for directory in (self.root, self._staging, self._artifacts, self._completions, self._attempts):
            directory.mkdir(parents=True, exist_ok=True)
        if not marker.exists():
            # Same discipline as records: staged and fsynced, then published by one exclusive link,
            # so a crash never leaves an empty or partial STORE.json.
            staged = self._stage("marker", expected)
            self._fault(MARKER_SEAM)
            self._publish(staged, marker)
            staged.unlink()
        if marker.read_bytes() != expected:
            raise RepeatContractError("STORE_IDENTITY", str(self.root))

    def _fault(self, seam: str) -> None:
        if self._fault_hook is not None:
            self._fault_hook(seam)

    def _stage(self, kind: str, data: bytes) -> Path:
        path = self._staging / f"{uuid4().hex}.{kind}"
        with open(path, "xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        return path

    @staticmethod
    def _publish(staged: Path, final: Path) -> bool:
        """Atomic and exclusive: the fully written file appears under ``final`` or not at all."""
        try:
            os.link(staged, final)
        except FileExistsError:
            return False
        if os.name == "posix":
            descriptor = os.open(final.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        return True

    def _blob(self, record: CompletionRecord) -> Path:
        return self._artifacts / f"{record.artifact_byte_hashes[0][1]}.json"

    def _read(self, repeat_id: str, deep: bool) -> StoredCoordinate | None:
        marker = self._completions / f"{digest_field(repeat_id, 'repeat_id')}.json"
        try:
            raw = marker.read_bytes()
        except FileNotFoundError:
            return None
        try:
            value = json.loads(raw.decode("ascii"))
            record = CompletionRecord(
                repeat_id=value["repeat_id"],
                logical_content_sha256=value["logical_content_sha256"],
                artifact_byte_hashes=tuple(tuple(pair) for pair in value["artifact_byte_hashes"]),
                terminal_status=value["terminal_status"],
            )
            if (
                value.get("schema") != STORE_SCHEMA or record.repeat_id != repeat_id
                or raw != _record_marker_bytes(record)
            ):
                raise ValueError("marker does not describe its own record")
            artifact = self._blob(record).read_bytes()
            result = verify_coordinate_artifact(self.plan, record, artifact, deep=deep)
        except (ValueError, KeyError, TypeError, OSError) as cause:
            raise RepeatContractError("CORRUPT_COMPLETION", repeat_id) from cause
        return StoredCoordinate(record, artifact, result)

    def load(self, repeat_id: str) -> StoredCoordinate | None:
        """The fully re-verified completion, None if absent; a damaged one is an error, not absence."""
        return self._read(repeat_id, deep=True)

    def _insert(self, record: CompletionRecord, artifact: bytes) -> CompletionDecision | Conflict:
        self._fault("before_stage")
        staged = self._stage("artifact", artifact)
        self._fault("after_stage_artifact")
        if not self._publish(staged, self._blob(record)):
            # Content-addressed bytes already exist; they must be exactly these bytes.
            if self._blob(record).read_bytes() != artifact:
                raise RepeatContractError("CORRUPT_COMPLETION", record.repeat_id)
        staged.unlink()
        self._fault("after_publish_artifact")
        staged = self._stage("record", _record_marker_bytes(record))
        self._fault("before_commit")
        # The commit point: before this link the repeat is not completed, after it it is.
        won = self._publish(staged, self._completions / f"{record.repeat_id}.json")
        if won:
            self._fault("after_commit")
        staged.unlink()
        if won:
            return INSERT
        return self._decide(record)

    def _decide(self, record: CompletionRecord) -> CompletionDecision | Conflict:
        """Insert/reuse/conflict against what is stored. A conflict is only reported against an
        existing record that fully re-verifies; a damaged one is corruption, never a conflict."""
        existing = self._read(record.repeat_id, deep=False)
        decision = completion_action(existing.record if existing else None, record)
        if isinstance(decision, Conflict):
            self._read(record.repeat_id, deep=True)
        return decision

    def commit(
        self,
        result: CoordinateResult,
        *,
        attempt_id: str,
        audit: Mapping[str, Any] | None = None,
    ) -> CommitResult:
        record, artifact = encode_coordinate(self.plan, result)
        self._require_new_attempt(record.repeat_id, attempt_id)
        decision = self._decide(record)
        if decision is INSERT:
            decision = self._insert(record, artifact)
        stored = self._read(record.repeat_id, deep=False)
        conflict = isinstance(decision, Conflict)
        self._record_attempt(
            record.repeat_id, attempt_id,
            "CONFLICT" if conflict else decision.name,
            decision.reason if conflict else None, audit,
        )
        return CommitResult(decision, stored.record)

    def record_failed_attempt(
        self,
        repeat_id: str,
        attempt_id: str,
        reason: str,
        audit: Mapping[str, Any] | None = None,
    ) -> None:
        """Append a failed attempt. It never counts as, or replaces, a completion."""
        digest_field(repeat_id, "repeat_id")
        identifier(reason, "reason", max_bytes=1024)
        self._require_new_attempt(repeat_id, attempt_id)
        self._record_attempt(repeat_id, attempt_id, "FAILED_ATTEMPT", reason, audit)

    def _attempt_files(self, repeat_id: str) -> list[tuple[int, str, Path]]:
        directory = self._attempts / digest_field(repeat_id, "repeat_id")
        if not directory.is_dir():
            return []
        found = []
        for path in directory.iterdir():
            match = _ATTEMPT_FILE.fullmatch(path.name)
            if match:
                found.append((int(match.group(1)), match.group(2), path))
        return sorted(found)

    def _require_new_attempt(self, repeat_id: str, attempt_id: str) -> None:
        if type(attempt_id) is not str or _ATTEMPT_ID.fullmatch(attempt_id) is None:
            raise RepeatContractError("IDENTIFIER", "attempt_id")
        if any(name == attempt_id for _, name, _ in self._attempt_files(repeat_id)):
            raise RepeatContractError("DUPLICATE_ATTEMPT", attempt_id)

    def _record_attempt(
        self,
        repeat_id: str,
        attempt_id: str,
        outcome: str,
        reason: str | None,
        audit: Mapping[str, Any] | None,
    ) -> None:
        directory = self._attempts / repeat_id
        directory.mkdir(exist_ok=True)
        # Runtime audit only: this never feeds a logical or byte hash, or any count.
        body = (canonical_json({
            "attempt_id": attempt_id,
            "outcome": outcome,
            "reason": reason,
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            "audit": dict(audit or {}),
        }) + "\n").encode("ascii")
        sequence = len(self._attempt_files(repeat_id))
        while True:
            try:
                with open(directory / f"{sequence:06d}-{attempt_id}.json", "xb") as handle:
                    handle.write(body)
                    handle.flush()
                    os.fsync(handle.fileno())
                return
            except FileExistsError:
                sequence += 1

    def attempts(self, repeat_id: str) -> tuple[AttemptRecord, ...]:
        records = []
        for _, _, path in self._attempt_files(repeat_id):
            value = json.loads(path.read_bytes().decode("ascii"))
            records.append(AttemptRecord(
                attempt_id=value["attempt_id"],
                outcome=value["outcome"],
                reason=value["reason"],
                recorded_at_utc=value["recorded_at_utc"],
                audit_json=canonical_json(value["audit"]),
            ))
        return tuple(records)

    def inventory(self) -> StoreInventory:
        """One deep scan: only fully re-verified coordinates count as completed (or failed)."""
        completed, failed, corrupt = [], [], []
        for path in sorted(self._completions.iterdir()):
            match = _REPEAT_FILE.fullmatch(path.name)
            if not match:
                continue
            try:
                record = self.load(match.group(1)).record
            except RepeatContractError:
                corrupt.append(match.group(1))
                continue
            (completed if record.terminal_status == "completed" else failed).append(record.repeat_id)
        return StoreInventory(tuple(completed), tuple(failed), tuple(corrupt))

    def completed_repeat_ids(self) -> tuple[str, ...]:
        """Completed coordinates, only those whose bytes, plan binding and content fully re-verify."""
        return self.inventory().completed

    def terminal_failure_ids(self) -> tuple[str, ...]:
        """Always empty today: this store only accepts completed coordinates."""
        return self.inventory().failed

    def corrupt_completion_ids(self) -> tuple[str, ...]:
        return self.inventory().corrupt

    def orphaned_staging(self) -> tuple[str, ...]:
        """Staging files left by interrupted attempts. They are reported, never removed."""
        return tuple(sorted(path.name for path in self._staging.iterdir()))
