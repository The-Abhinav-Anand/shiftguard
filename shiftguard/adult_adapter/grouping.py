"""Label-blind exact-feature groups, test-connected quarantine and grouped role allocation.

A candidate profile for the Gate 8 grouped-allocation amendment, exercised on
fabricated rows. It does not replace ``make_adult_role_splits``, uses no label,
and its output is an allocation proposal, never evidence about any outcome.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from shiftguard.adult_adapter.features import (
    ADULT_FEATURE_CONTRACT,
    DEVELOPMENT_SOURCE_FILE,
    AdultAdapterError,
    AdultFeatureContract,
    AdultRecord,
    canonical_digest,
    canonical_json,
    digest_field,
    immutable_tuple,
    strict_int,
)
from shiftguard.datasets.adult import ADULT_ROLE_FRACTIONS


FEATURE_GROUP_VERSION = "gate8-feature-group-v1"
GROUP_ORDER_VERSION = "gate8-group-order-v1"
ALLOCATION_VERSION = "gate9-adult-grouped-allocation-v1"
QUARANTINE_REASON = "test_connected_exact_feature_group"
MINIMUM_POOL_ROWS = 200

# Fixed order doubles as the tie-break order for equal deficits.
ROLES = ("train", "source_cal", "target_pool")
# Fractions come from the parser's constants; they are dyadic, so Fraction(float) is exact.
ROLE_FRACTIONS = tuple(Fraction(ADULT_ROLE_FRACTIONS[role]) for role in ROLES)


def group_key(record: AdultRecord, contract: AdultFeatureContract = ADULT_FEATURE_CONTRACT) -> str:
    """SHA-256 of ``[version, schema_digest, ordered raw tokens or null]``.

    Row id, source file and labels are absent by construction, so the same feature vector
    gets the same key in adult.data and adult.test; only ``None`` means a missing marker.
    """
    payload = canonical_json([FEATURE_GROUP_VERSION, contract.schema_digest, list(record.tokens)])
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def _development_records(records: Any) -> tuple[AdultRecord, ...]:
    rows = immutable_tuple(records, "records")
    seen: set[str] = set()
    for record in rows:
        if type(record) is not AdultRecord:
            raise AdultAdapterError("RECORD_TYPE", "records")
        if record.source.source_file != DEVELOPMENT_SOURCE_FILE:
            raise AdultAdapterError("NON_DEVELOPMENT_ROW", record.row_id)
        if record.row_id in seen:
            raise AdultAdapterError("DUPLICATE_ROW_ID", record.row_id)
        seen.add(record.row_id)
    return rows


def _group_members(rows: tuple[AdultRecord, ...]) -> dict[str, list[AdultRecord]]:
    groups: dict[str, list[AdultRecord]] = {}
    for record in rows:
        groups.setdefault(group_key(record), []).append(record)
    for members in groups.values():
        members.sort(key=lambda r: r.source.order_key)
    return groups


@dataclass(frozen=True)
class QuarantineResult:
    retained: tuple[AdultRecord, ...]
    quarantined_row_ids: tuple[str, ...]
    quarantined_group_ids: tuple[str, ...]
    declared_group_count: int
    declared_groups_absent_count: int
    original_row_count: int
    quarantined_row_count: int
    retained_row_count: int
    original_group_count: int
    retained_group_count: int
    reason: str = QUARANTINE_REASON


def quarantine_test_connected(records: Any, test_connected_group_keys: Any) -> QuarantineResult:
    """Drop every development row whose group is declared test-connected, before any allocation.

    The keys are supplied by the caller (e.g. a future custodian manifest); membership is
    exact-feature only. Dropping the whole group keeps a duplicate from straddling roles.
    """
    rows = _development_records(records)
    if type(test_connected_group_keys) not in (set, frozenset):
        raise AdultAdapterError("GROUP_KEY_SET", "test_connected_group_keys")
    declared = {digest_field(key, "group_key") for key in test_connected_group_keys}
    groups = _group_members(rows)
    hit = sorted(declared & groups.keys())
    gone = [record for key in hit for record in groups[key]]
    gone.sort(key=lambda r: r.source.order_key)
    gone_ids = {record.row_id for record in gone}
    retained = tuple(sorted((r for r in rows if r.row_id not in gone_ids), key=lambda r: r.source.order_key))
    return QuarantineResult(
        retained=retained,
        quarantined_row_ids=tuple(record.row_id for record in gone),
        quarantined_group_ids=tuple(hit),
        declared_group_count=len(declared),
        declared_groups_absent_count=len(declared) - len(hit),
        original_row_count=len(rows),
        quarantined_row_count=len(gone),
        retained_row_count=len(retained),
        original_group_count=len(groups),
        retained_group_count=len(groups) - len(hit),
    )


@dataclass(frozen=True)
class RoleAllocation:
    role: str
    row_ids: tuple[str, ...]  # appended group by group, members in numeric source-qualified order
    group_ids: tuple[str, ...]
    target_fraction: float
    target_rows: float
    achieved_fraction: float
    deviation_rows: float

    @property
    def row_count(self) -> int:
        return len(self.row_ids)

    @property
    def group_count(self) -> int:
        return len(self.group_ids)


@dataclass(frozen=True)
class GroupedAllocation:
    split_seed: int
    status: str  # "OK" or "UNSUPPORTED_ROLE"
    unsupported_roles: tuple[str, ...]
    roles: tuple[RoleAllocation, ...]
    row_count: int
    group_count: int
    largest_group_rows: int
    minimum_pool_rows: int
    allocation_digest: str

    def role(self, name: str) -> RoleAllocation:
        for allocation in self.roles:
            if allocation.role == name:
                return allocation
        raise AdultAdapterError("ROLE", name)

    def require_supported(self) -> None:
        """Memberships are reported even when unsupported; callers must not train on them."""
        if self.status != "OK":
            raise AdultAdapterError("UNSUPPORTED_ROLE", ",".join(self.unsupported_roles))


def allocate_grouped_roles(
    records: Any, split_seed: Any, minimum_pool_rows: int = MINIMUM_POOL_ROWS
) -> GroupedAllocation:
    """Deterministic largest-deficit allocation of whole exact-feature groups; labels never used.

    Groups are ordered by SHA-256 of ``["gate8-group-order-v1", split_seed, group_id]``
    (ties by group id), then each goes to the role with the largest ``target - assigned``
    rows, ties in ROLES order. Targets are exact rationals, so there is no float tie noise.
    """
    seed = strict_int(split_seed, "split_seed", code="SEED_TYPE")
    floor = strict_int(minimum_pool_rows, "minimum_pool_rows")
    rows = _development_records(records)
    groups = _group_members(rows)
    n = len(rows)
    targets = [n * fraction for fraction in ROLE_FRACTIONS]
    assigned = [0, 0, 0]
    row_ids: list[list[str]] = [[], [], []]
    group_ids: list[list[str]] = [[], [], []]

    def order(group_id: str) -> tuple[str, str]:
        digest = hashlib.sha256(canonical_json([GROUP_ORDER_VERSION, seed, group_id]).encode("ascii"))
        return (digest.hexdigest(), group_id)

    for group_id in sorted(groups, key=order):
        # max() keeps the first maximum, which is the fixed tie order.
        slot = max(range(3), key=lambda i: targets[i] - assigned[i])
        members = groups[group_id]
        row_ids[slot].extend(member.row_id for member in members)
        group_ids[slot].append(group_id)
        assigned[slot] += len(members)

    roles = tuple(
        RoleAllocation(
            role=ROLES[i],
            row_ids=tuple(row_ids[i]),
            group_ids=tuple(group_ids[i]),
            target_fraction=float(ROLE_FRACTIONS[i]),
            target_rows=float(targets[i]),
            achieved_fraction=assigned[i] / n if n else 0.0,
            deviation_rows=float(assigned[i] - targets[i]),
        )
        for i in range(3)
    )
    unsupported = tuple(role.role for role in roles if role.row_count == 0)
    pool = roles[ROLES.index("target_pool")]
    if pool.row_count < floor and "target_pool" not in unsupported:
        unsupported += ("target_pool",)
    unsupported = tuple(name for name in ROLES if name in unsupported)
    return GroupedAllocation(
        split_seed=seed,
        status="UNSUPPORTED_ROLE" if unsupported else "OK",
        unsupported_roles=unsupported,
        roles=roles,
        row_count=n,
        group_count=len(groups),
        largest_group_rows=max((len(m) for m in groups.values()), default=0),
        minimum_pool_rows=floor,
        allocation_digest=canonical_digest([
            ALLOCATION_VERSION, seed, {role.role: list(role.row_ids) for role in roles},
        ]),
    )
