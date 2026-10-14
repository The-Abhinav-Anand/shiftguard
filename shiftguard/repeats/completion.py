"""Logical restart contract for one synthetic repeat completion.

A completion is immutable content keyed by its full repeat ID. Its logical
identity is the canonical JSON digest of plan, repeat, terminal status and
content; the hash of the serialized UTF-8/LF bytes is kept separately. Runtime
metadata such as attempt IDs, timestamps, paths and scheduling order is audit
information and never enters either hash.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Any, Mapping

from shiftguard.repeats.models import (
    RepeatContractError,
    RepeatPlan,
    canonical_json,
    digest_field,
    identifier,
    immutable_tuple,
)
from shiftguard.repeats.planning import ensure_planned


TERMINAL_STATUSES = ("completed", "failed")
ARTIFACT_NAME = "completion.json"
_ENVELOPE_KEYS = {"content", "plan_digest", "repeat_id", "terminal_status"}
_RUNTIME_KEYS = frozenset({
    "attempt_id", "attempt_uuid", "execution_id", "uuid", "timestamp", "created_at",
    "started_at", "completed_at", "updated_at", "recorded_at_utc", "host", "hostname",
    "host_path", "path", "scheduled_order", "worker_id",
})


class CompletionDecision(Enum):
    INSERT = "INSERT"
    IDEMPOTENT_REUSE = "IDEMPOTENT_REUSE"


INSERT = CompletionDecision.INSERT
IDEMPOTENT_REUSE = CompletionDecision.IDEMPOTENT_REUSE


@dataclass(frozen=True)
class CompletionRecord:
    repeat_id: str
    logical_content_sha256: str
    artifact_byte_hashes: tuple[tuple[str, str], ...]
    terminal_status: str

    def __post_init__(self) -> None:
        digest_field(self.repeat_id, "repeat_id")
        digest_field(self.logical_content_sha256, "logical_content_sha256")
        pairs = immutable_tuple(self.artifact_byte_hashes, "artifact_byte_hashes")
        if not pairs:
            raise RepeatContractError("EMPTY_VALUE", "artifact_byte_hashes")
        names = []
        for pair in pairs:
            if type(pair) is not tuple or len(pair) != 2:
                raise RepeatContractError("IMMUTABLE_TUPLE", "artifact_byte_hashes")
            names.append(identifier(pair[0], "artifact_byte_hashes"))
            digest_field(pair[1], "artifact_byte_hashes")
        if names != sorted(set(names)):
            raise RepeatContractError("DUPLICATE_VALUE", "artifact_byte_hashes")
        if self.terminal_status not in TERMINAL_STATUSES:
            raise RepeatContractError("TERMINAL_STATUS", repr(self.terminal_status))


@dataclass(frozen=True)
class Conflict:
    """The same repeat ID already holds different immutable content."""

    repeat_id: str
    existing_logical_sha256: str
    incoming_logical_sha256: str
    reason: str


def completion_action(
    existing: CompletionRecord | None,
    incoming: CompletionRecord,
) -> CompletionDecision | Conflict:
    """Pure decision: insert once, reuse an identical retry, never overwrite."""
    if type(incoming) is not CompletionRecord or (
        existing is not None and type(existing) is not CompletionRecord
    ):
        raise RepeatContractError("REPEAT_SCHEMA", "completion record")
    if existing is None:
        return INSERT
    if existing.repeat_id != incoming.repeat_id:
        raise RepeatContractError("REPEAT_ID_MISMATCH", incoming.repeat_id)
    if existing == incoming:
        return IDEMPOTENT_REUSE
    if existing.logical_content_sha256 != incoming.logical_content_sha256:
        reason = "logical_content_differs"
    elif existing.terminal_status != incoming.terminal_status:
        reason = "terminal_status_differs"
    else:
        reason = "artifact_bytes_differ"
    return Conflict(
        repeat_id=incoming.repeat_id,
        existing_logical_sha256=existing.logical_content_sha256,
        incoming_logical_sha256=incoming.logical_content_sha256,
        reason=reason,
    )


def serialize_artifact(value: Any) -> bytes:
    """Canonical JSON with one trailing LF; ASCII, so also valid UTF-8."""
    try:
        return (canonical_json(value) + "\n").encode("ascii")
    except (TypeError, ValueError):
        raise RepeatContractError("CONTENT_NOT_CANONICAL") from None


def _runtime_keys(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, str) and key.lower() in _RUNTIME_KEYS:
                found.add(key)
            found |= _runtime_keys(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            found |= _runtime_keys(item)
    return found


def _require_fabricated(content: Any) -> None:
    # This slice persists fabricated fixtures only; nothing real may be stored through it.
    if not isinstance(content, Mapping) or content.get("synthetic") is not True:
        raise RepeatContractError("SYNTHETIC_ONLY", "content")
    runtime = _runtime_keys(content)
    if runtime:
        raise RepeatContractError("RUNTIME_METADATA_IN_IDENTITY", ", ".join(sorted(runtime)))


def _record_for(repeat_id: str, terminal_status: str, artifact: bytes) -> CompletionRecord:
    return CompletionRecord(
        repeat_id=repeat_id,
        logical_content_sha256=hashlib.sha256(artifact[:-1]).hexdigest(),
        artifact_byte_hashes=((ARTIFACT_NAME, hashlib.sha256(artifact).hexdigest()),),
        terminal_status=terminal_status,
    )


def build_completion(
    plan: RepeatPlan,
    repeat_id: str,
    content: Mapping[str, Any],
    terminal_status: str,
) -> tuple[CompletionRecord, bytes]:
    """Bind fabricated content to its plan and repeat; returns the record and its bytes."""
    ensure_planned(plan)
    if terminal_status not in TERMINAL_STATUSES:
        raise RepeatContractError("TERMINAL_STATUS", repr(terminal_status))
    if repeat_id not in {repeat.repeat_id for repeat in plan.repeats}:
        raise RepeatContractError("UNDECLARED_REPEAT", str(repeat_id))
    _require_fabricated(content)
    artifact = serialize_artifact({
        "content": content,
        "plan_digest": plan.plan_digest,
        "repeat_id": repeat_id,
        "terminal_status": terminal_status,
    })
    return _record_for(repeat_id, terminal_status, artifact), artifact


def verify_artifact(record: CompletionRecord, artifact: bytes) -> None:
    """Check that bytes are the canonical, fabricated content their record names."""
    if type(record) is not CompletionRecord or type(artifact) is not bytes:
        raise RepeatContractError("REPEAT_SCHEMA", "record/artifact")
    if record.artifact_byte_hashes != ((ARTIFACT_NAME, hashlib.sha256(artifact).hexdigest()),):
        raise RepeatContractError("ARTIFACT_HASH_MISMATCH", record.repeat_id)
    try:
        envelope = json.loads(artifact.decode("ascii"))
    except (UnicodeDecodeError, ValueError):
        raise RepeatContractError("ARTIFACT_NOT_CANONICAL", record.repeat_id) from None
    if serialize_artifact(envelope) != artifact:
        raise RepeatContractError("ARTIFACT_NOT_CANONICAL", record.repeat_id)
    if record.logical_content_sha256 != hashlib.sha256(artifact[:-1]).hexdigest():
        raise RepeatContractError("LOGICAL_HASH_MISMATCH", record.repeat_id)
    if (
        not isinstance(envelope, dict)
        or set(envelope) != _ENVELOPE_KEYS
        or envelope["repeat_id"] != record.repeat_id
        or envelope["terminal_status"] != record.terminal_status
    ):
        raise RepeatContractError("ARTIFACT_ENVELOPE", record.repeat_id)
    _require_fabricated(envelope["content"])
