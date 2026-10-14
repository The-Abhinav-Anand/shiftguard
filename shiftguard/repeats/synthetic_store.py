"""Isolated, restart-safe filesystem store for fabricated repeat completions.

Not a migration, not a public API and not a workflow engine. Bytes are staged
and fsynced first; a repeat counts as completed only once its record has been
published by one atomic, exclusive hard link under its full repeat ID. Nothing
is ever overwritten, and interrupted staging files and failed attempts are kept.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Any, Callable, Mapping
from uuid import uuid4

from shiftguard.repeats.completion import (
    INSERT,
    CompletionDecision,
    CompletionRecord,
    Conflict,
    completion_action,
    verify_artifact,
)
from shiftguard.repeats.models import (
    RepeatContractError,
    canonical_json,
    digest_field,
    identifier,
)


STORE_SCHEMA = "gate8-synthetic-repeat-store-v1"
# Named persistence seams, in order, where a fault hook may stop the process.
SEAMS = (
    "before_stage", "after_stage_artifact", "after_publish_artifact",
    "before_commit", "after_commit",
)
_STORE_MARKER = (canonical_json({"schema": STORE_SCHEMA, "synthetic_only": True}) + "\n").encode("ascii")
_ATTEMPT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
_ATTEMPT_FILE = re.compile(r"(\d{6})-([A-Za-z0-9][A-Za-z0-9_-]{0,63})\.json")
_REPEAT_FILE = re.compile(r"([0-9a-f]{64})\.json")


@dataclass(frozen=True)
class StoredCompletion:
    record: CompletionRecord
    artifact: bytes


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


def _marker_bytes(record: CompletionRecord) -> bytes:
    return (canonical_json({
        "schema": STORE_SCHEMA,
        "repeat_id": record.repeat_id,
        "logical_content_sha256": record.logical_content_sha256,
        "artifact_byte_hashes": [list(pair) for pair in record.artifact_byte_hashes],
        "terminal_status": record.terminal_status,
    }) + "\n").encode("ascii")


class SyntheticRepeatStore:
    def __init__(self, root: Path, *, fault: Callable[[str], None] | None = None) -> None:
        self.root = Path(root)
        self._fault_hook = fault
        marker = self.root / "STORE.json"
        if self.root.exists():
            foreign = not self.root.is_dir() or (
                any(self.root.iterdir())
                and not (marker.is_file() and marker.read_bytes() == _STORE_MARKER)
            )
            if foreign:
                raise RepeatContractError("STORE_IDENTITY", str(self.root))
        self._staging = self.root / "staging"
        self._artifacts = self.root / "artifacts"
        self._completions = self.root / "completions"
        self._attempts = self.root / "attempts"
        for directory in (self.root, self._staging, self._artifacts, self._completions, self._attempts):
            directory.mkdir(parents=True, exist_ok=True)
        try:
            with open(marker, "xb") as handle:
                handle.write(_STORE_MARKER)
        except FileExistsError:
            if marker.read_bytes() != _STORE_MARKER:
                raise RepeatContractError("STORE_IDENTITY", str(self.root)) from None

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

    def load(self, repeat_id: str) -> StoredCompletion | None:
        """The committed completion, None if absent; a damaged one is an error, not absence."""
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
            if record.repeat_id != repeat_id or raw != _marker_bytes(record):
                raise ValueError("marker does not describe its own record")
            artifact = self._blob(record).read_bytes()
            verify_artifact(record, artifact)
        except (ValueError, KeyError, TypeError, OSError):
            raise RepeatContractError("CORRUPT_COMPLETION", repeat_id) from None
        return StoredCompletion(record, artifact)

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
        staged = self._stage("record", _marker_bytes(record))
        self._fault("before_commit")
        # The commit point: before this link the repeat is not completed, after it it is.
        won = self._publish(staged, self._completions / f"{record.repeat_id}.json")
        if won:
            self._fault("after_commit")
        staged.unlink()
        if won:
            return INSERT
        return completion_action(self.load(record.repeat_id).record, record)

    def commit(
        self,
        record: CompletionRecord,
        artifact: bytes,
        *,
        attempt_id: str,
        audit: Mapping[str, Any] | None = None,
    ) -> CommitResult:
        verify_artifact(record, artifact)
        self._require_new_attempt(record.repeat_id, attempt_id)
        existing = self.load(record.repeat_id)
        decision = completion_action(existing.record if existing else None, record)
        if decision is INSERT:
            decision = self._insert(record, artifact)
        stored = self.load(record.repeat_id)
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

    def _committed(self) -> tuple[list[CompletionRecord], list[str]]:
        records, corrupt = [], []
        for path in sorted(self._completions.iterdir()):
            match = _REPEAT_FILE.fullmatch(path.name)
            if not match:
                continue
            try:
                records.append(self.load(match.group(1)).record)
            except RepeatContractError:
                corrupt.append(match.group(1))
        return records, corrupt

    def completed_repeat_ids(self) -> tuple[str, ...]:
        """Completed repeats, derived only from intact committed records."""
        return tuple(
            record.repeat_id for record in self._committed()[0]
            if record.terminal_status == "completed"
        )

    def terminal_failure_ids(self) -> tuple[str, ...]:
        return tuple(
            record.repeat_id for record in self._committed()[0]
            if record.terminal_status == "failed"
        )

    def corrupt_completion_ids(self) -> tuple[str, ...]:
        return tuple(self._committed()[1])

    def orphaned_staging(self) -> tuple[str, ...]:
        """Staging files left by interrupted attempts. They are reported, never removed."""
        return tuple(sorted(path.name for path in self._staging.iterdir()))
