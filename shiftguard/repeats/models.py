"""Immutable contracts for the synthetic Gate 8 repeat-engineering slice.

These types are prospective plumbing exercised with fabricated fixtures only.
Nothing here imports a loader, runner, evaluator or provider, and constructing
them neither locks the protocol nor permits confirmatory dispatch.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
import hashlib
import json
import math
import re
from typing import Any, NamedTuple


SCHEMA_VERSION = "gate8-repeat-engineering-v1"
EXECUTION_MODE = "synthetic_only"
PROTOCOL_VERSION = "shiftguard.research.protocol-draft.v0.3"
SEED_ALGORITHM_VERSION = "gate8-nested-v1"
NUMPY_VERSION = "2.5.3"

OUTER_SEEDS = (41001, 41002, 41003, 41004, 41005)
INNER_IDS = (51001, 51002, 51003, 51004, 51005, 51006, 51007, 51008, 51009, 51010)
PREDICTORS = ("logistic_regression", "random_forest")
SCENARIOS = (
    "baseline", "history_block_0_50", "mcar_0_10", "mcar_0_30", "mcar_matched_history",
)
PRIMARY_SCENARIOS = SCENARIOS[1:]
BUDGETS = (0, 25, 50, 100, 200)
METHODS = (
    "raw", "source_temperature", "source_remasked_temperature",
    "source_fraction_binned_temperature", "target_temperature",
    "target_platt_logodds", "target_beta", "target_isotonic",
)
PRIMARY_TARGET_METHOD = "target_temperature"
PRIMARY_SOURCE_METHOD = "source_fraction_binned_temperature"
PRIMARY_BUDGET = 50
# Each requested method resolves down its own chain only. Mirrors
# experiments.stress_runner.STRESS_FALLBACK_GRAPH, which cannot be imported here
# without pulling in publication and storage; a test pins the two together.
FALLBACK_GRAPH = {
    "raw": None,
    "source_temperature": "raw",
    "source_remasked_temperature": "source_temperature",
    "source_fraction_binned_temperature": "source_remasked_temperature",
    "target_temperature": "source_temperature",
    "target_platt_logodds": "target_temperature",
    "target_beta": "target_platt_logodds",
    "target_isotonic": "target_temperature",
}
MINIMUM_POOL_ROWS = max(BUDGETS)

QUALIFICATIONS = ("qualified", "unqualified", "unknown_authority", "failed")
EXPOSURE_STATUSES = (
    "synthetic_fabricated", "development_exposed", "unknown", "custodian_attested",
)
SYNTHETIC_EXPOSURE = "synthetic_fabricated"
SYNTHETIC_CLAIM_SCOPE = "synthetic_engineering_fixture_not_a_research_finding"
# Stored record versions. v1 of the paired cell carried no resolution accounting; nothing
# may invent it on read, so only the current version is accepted.
PAIRED_CELL_RECORD_VERSION = "gate8-paired-cell-v2"
TERMINAL_CONDITION_RECORD_VERSION = "gate8-terminal-condition-v1"

_DIGEST = re.compile(r"[0-9a-f]{64}")


class RepeatContractError(ValueError):
    """A typed rejection; ``code`` is stable, ``detail`` names the offending field."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )


def canonical_digest(value: Any) -> str:
    """Logical identity: SHA-256 of canonical ASCII JSON, never of file bytes."""
    return hashlib.sha256(canonical_json(value).encode("ascii")).hexdigest()


def strict_int(value: Any, name: str) -> int:
    if type(value) is not int:
        raise RepeatContractError("STRICT_INTEGER", name)
    return value


def strict_bool(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise RepeatContractError("STRICT_BOOLEAN", name)
    return value


def immutable_tuple(value: Any, name: str) -> tuple:
    if type(value) is not tuple:
        raise RepeatContractError("IMMUTABLE_TUPLE", name)
    return value


def identifier(value: Any, name: str, max_bytes: int = 256) -> str:
    if (
        type(value) is not str
        or not value
        or len(value.encode("utf-8")) > max_bytes
        or any(ord(char) < 32 for char in value)
    ):
        raise RepeatContractError("IDENTIFIER", name)
    return value


def digest_field(value: Any, name: str) -> str:
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        raise RepeatContractError("DIGEST", name)
    return value


def unique(values: tuple, name: str) -> tuple:
    if len(set(values)) != len(values):
        raise RepeatContractError("DUPLICATE_VALUE", name)
    return values


def identifier_tuple(value: Any, name: str) -> tuple[str, ...]:
    for item in immutable_tuple(value, name):
        identifier(item, name)
    return value


def declared(value: Any, allowed: tuple, name: str) -> Any:
    if value not in allowed:
        raise RepeatContractError("UNDECLARED_VALUE", name)
    return value


def declared_repeat(outer_seed: int, inner_id: int) -> None:
    strict_int(outer_seed, "outer_seed")
    strict_int(inner_id, "inner_id")
    if outer_seed not in OUTER_SEEDS or inner_id not in INNER_IDS:
        raise RepeatContractError("UNDECLARED_REPEAT", f"{outer_seed}/{inner_id}")


def _exact(value: Any, expected: Any, code: str) -> None:
    if type(value) is not type(expected) or value != expected:
        raise RepeatContractError(code, repr(value))


def fallback_chain(method: str) -> tuple[str, ...]:
    """The requested method followed by every method it may resolve through, ending at raw."""
    declared(method, METHODS, "requested_method")
    chain = []
    current: str | None = method
    while current is not None:
        chain.append(current)
        current = FALLBACK_GRAPH[current]
    return tuple(chain)


def validate_resolution_accounting(
    requested: str, resolved: str | None, counts: Any, name: str
) -> int:
    """Check one resolution tally and return its total row count.

    Entries are unique, strictly positive and in declared method order. Every entry lies on
    the requested method's fallback chain. Only the fraction-binned strategy may mix
    resolutions across rows; every other strategy resolves its whole condition to one method.
    """
    entries = immutable_tuple(counts, name)
    previous, total = -1, 0
    for pair in entries:
        if type(pair) is not tuple or len(pair) != 2:
            raise RepeatContractError("IMMUTABLE_TUPLE", name)
        method = declared(pair[0], METHODS, name)
        count = strict_int(pair[1], name)
        if count < 0:
            raise RepeatContractError("NEGATIVE_COUNT", name)
        if count == 0:
            raise RepeatContractError("RESOLUTION_ACCOUNTING", f"{name}: zero-count entry")
        position = METHODS.index(method)
        if position <= previous:
            raise RepeatContractError("RESOLUTION_ACCOUNTING", f"{name}: duplicate or unordered entry")
        previous = position
        total += count
    if resolved is None:
        if entries:
            raise RepeatContractError("RESOLUTION_ACCOUNTING", f"{name}: counts without a resolution")
        return 0
    if not entries:
        raise RepeatContractError("RESOLUTION_ACCOUNTING", f"{name}: resolution without counts")
    if requested in METHODS:
        chain = fallback_chain(requested)
        if resolved not in chain or any(pair[0] not in chain for pair in entries):
            raise RepeatContractError("FORBIDDEN_FALLBACK", f"{name}: {requested} -> {resolved}")
        mixed_allowed = requested == resolved == "source_fraction_binned_temperature"
        if not mixed_allowed and entries != ((resolved, total),):
            raise RepeatContractError("RESOLUTION_ACCOUNTING", f"{name}: mixed resolution not declared")
    elif entries != ((resolved, total),):
        raise RepeatContractError("RESOLUTION_ACCOUNTING", f"{name}: mixed resolution not declared")
    return total


def fallback_row_count(requested: str, counts: tuple[tuple[str, int], ...]) -> int:
    """Rows that resolved to anything other than the requested method."""
    return sum(count for method, count in counts if method != requested)


def tuplify(value: Any) -> Any:
    """JSON lists back to the tuples every contract demands."""
    if isinstance(value, list):
        return tuple(tuplify(item) for item in value)
    return value


def _stored_fields(value: Any, owner: type, version: str, label: str) -> dict[str, Any]:
    """Validate a stored record's version and key set; unknown versions are never reinterpreted."""
    if not isinstance(value, dict) or "record_version" not in value:
        raise RepeatContractError("RECORD_VERSION", f"{label}: missing record_version")
    if value["record_version"] != version:
        raise RepeatContractError(
            "RECORD_VERSION",
            f"{label}: stored version {value['record_version']!r} is not readable as {version!r}",
        )
    fields = {key: item for key, item in value.items() if key != "record_version"}
    if set(fields) != set(owner.__dataclass_fields__):
        raise RepeatContractError("RECORD_FIELDS", label)
    return fields


@dataclass(frozen=True)
class RepeatSpec:
    """The one reviewed 5x10 design; any alteration needs a prospective amendment."""

    schema_version: str = SCHEMA_VERSION
    execution_mode: str = EXECUTION_MODE
    confirmatory_dispatch_permitted: bool = False
    protocol_version: str = PROTOCOL_VERSION
    seed_algorithm_version: str = SEED_ALGORITHM_VERSION
    numpy_version: str = NUMPY_VERSION
    outer_seeds: tuple[int, ...] = OUTER_SEEDS
    inner_ids: tuple[int, ...] = INNER_IDS
    predictors: tuple[str, ...] = PREDICTORS
    scenarios: tuple[str, ...] = SCENARIOS
    budgets: tuple[int, ...] = BUDGETS
    methods: tuple[str, ...] = METHODS

    def __post_init__(self) -> None:
        _exact(self.schema_version, SCHEMA_VERSION, "SCHEMA_VERSION")
        _exact(self.execution_mode, EXECUTION_MODE, "EXECUTION_MODE")
        if self.confirmatory_dispatch_permitted is not False:
            raise RepeatContractError("CONFIRMATORY_DISPATCH_FORBIDDEN")
        _exact(self.protocol_version, PROTOCOL_VERSION, "PROTOCOL_VERSION")
        _exact(self.seed_algorithm_version, SEED_ALGORITHM_VERSION, "SEED_ALGORITHM_VERSION")
        _exact(self.numpy_version, NUMPY_VERSION, "NUMPY_VERSION")
        for name, expected, integers in (
            ("outer_seeds", OUTER_SEEDS, True),
            ("inner_ids", INNER_IDS, True),
            ("predictors", PREDICTORS, False),
            ("scenarios", SCENARIOS, False),
            ("budgets", BUDGETS, True),
            ("methods", METHODS, False),
        ):
            values = immutable_tuple(getattr(self, name), name)
            if not values:
                raise RepeatContractError("EMPTY_VALUE", name)
            for item in values:
                strict_int(item, name) if integers else identifier(item, name)
            unique(values, name)
            if values != expected:
                raise RepeatContractError("ALTERED_GRID", name)

    def to_canonical(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "execution_mode": self.execution_mode,
            "confirmatory_dispatch_permitted": self.confirmatory_dispatch_permitted,
            "protocol_version": self.protocol_version,
            "seed_algorithm_version": self.seed_algorithm_version,
            "numpy_version": self.numpy_version,
            "outer_seeds": list(self.outer_seeds),
            "inner_ids": list(self.inner_ids),
            "predictors": list(self.predictors),
            "scenarios": list(self.scenarios),
            "budgets": list(self.budgets),
            "methods": list(self.methods),
        }

    @cached_property
    def digest(self) -> str:
        return canonical_digest(self.to_canonical())


@dataclass(frozen=True)
class RepeatKey:
    outer_seed: int
    inner_id: int

    def __post_init__(self) -> None:
        strict_int(self.outer_seed, "outer_seed")
        strict_int(self.inner_id, "inner_id")


@dataclass(frozen=True)
class SeedMap:
    """Every derived stream of one execution coordinate, as sorted name/int pairs."""

    algorithm_version: str
    outer_seed: int
    inner_id: int
    numpy_version: str
    seeds: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        identifier(self.algorithm_version, "algorithm_version")
        identifier(self.numpy_version, "numpy_version")
        strict_int(self.outer_seed, "outer_seed")
        strict_int(self.inner_id, "inner_id")
        names = []
        for pair in immutable_tuple(self.seeds, "seeds"):
            if type(pair) is not tuple or len(pair) != 2:
                raise RepeatContractError("IMMUTABLE_TUPLE", "seeds")
            names.append(identifier(pair[0], "seeds"))
            strict_int(pair[1], "seeds")
        if not names or names != sorted(set(names)):
            raise RepeatContractError("SEED_MAP_ORDER", "seeds")

    def to_canonical(self) -> dict[str, Any]:
        return {
            "algorithm_version": self.algorithm_version,
            "outer_seed": self.outer_seed,
            "inner_id": self.inner_id,
            "numpy_version": self.numpy_version,
            "seeds": [list(pair) for pair in self.seeds],
        }

    @cached_property
    def digest(self) -> str:
        return canonical_digest(self.to_canonical())


@dataclass(frozen=True)
class SourceBinding:
    dataset: str
    release: str
    raw_sha256: str
    clean_sha256: str
    feature_schema_sha256: str
    group_manifest_sha256: str
    source_sha256: str
    dependency_lock_sha256: str
    protocol_review_sha256: str
    exposure_status: str

    def __post_init__(self) -> None:
        identifier(self.dataset, "dataset")
        identifier(self.release, "release")
        for name in (
            "raw_sha256", "clean_sha256", "feature_schema_sha256", "group_manifest_sha256",
            "source_sha256", "dependency_lock_sha256", "protocol_review_sha256",
        ):
            digest_field(getattr(self, name), name)
        if self.exposure_status not in EXPOSURE_STATUSES:
            raise RepeatContractError("EXPOSURE_STATUS", repr(self.exposure_status))

    def to_canonical(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}

    @cached_property
    def digest(self) -> str:
        return canonical_digest(self.to_canonical())


@dataclass(frozen=True)
class OuterRoleManifest:
    """Ordered role membership of one outer repeat with its evaluation groups."""

    outer_seed: int
    split_profile: str
    train_ids: tuple[str, ...]
    source_cal_ids: tuple[str, ...]
    target_pool_ids: tuple[str, ...]
    evaluation_ids: tuple[str, ...]
    evaluation_groups: tuple[str, ...]
    evaluation_order_digest: str

    def __post_init__(self) -> None:
        strict_int(self.outer_seed, "outer_seed")
        identifier(self.split_profile, "split_profile", max_bytes=64)
        seen: set[str] = set()
        for name in ("train_ids", "source_cal_ids", "target_pool_ids", "evaluation_ids"):
            members = unique(identifier_tuple(getattr(self, name), name), name)
            if seen.intersection(members):
                raise RepeatContractError("ROLE_OVERLAP", name)
            seen.update(members)
        identifier_tuple(self.evaluation_groups, "evaluation_groups")
        if len(self.evaluation_groups) != len(self.evaluation_ids):
            raise RepeatContractError("GROUP_MAP", "evaluation_groups")
        digest_field(self.evaluation_order_digest, "evaluation_order_digest")
        if self.evaluation_order_digest != canonical_digest(list(self.evaluation_ids)):
            raise RepeatContractError("EVALUATION_ORDER_DIGEST", str(self.outer_seed))

    @property
    def train_count(self) -> int:
        return len(self.train_ids)

    @property
    def source_cal_count(self) -> int:
        return len(self.source_cal_ids)

    @property
    def target_pool_count(self) -> int:
        return len(self.target_pool_ids)

    @property
    def support_status(self) -> str:
        supported = (
            self.train_ids and self.source_cal_ids and self.evaluation_ids
            and len(self.target_pool_ids) >= MINIMUM_POOL_ROWS
        )
        return "supported" if supported else "UNSUPPORTED_ROLE"

    @cached_property
    def group_map(self) -> tuple[tuple[str, str], ...]:
        return tuple(zip(self.evaluation_ids, self.evaluation_groups))

    @cached_property
    def group_row_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for group in self.evaluation_groups:
            counts[group] = counts.get(group, 0) + 1
        return counts

    def to_canonical(self) -> dict[str, Any]:
        return {
            "outer_seed": self.outer_seed,
            "split_profile": self.split_profile,
            "train_ids": list(self.train_ids),
            "source_cal_ids": list(self.source_cal_ids),
            "target_pool_ids": list(self.target_pool_ids),
            "evaluation_ids": list(self.evaluation_ids),
            "evaluation_groups": list(self.evaluation_groups),
            "evaluation_order_digest": self.evaluation_order_digest,
        }

    @cached_property
    def digest(self) -> str:
        return canonical_digest(self.to_canonical())


@dataclass(frozen=True)
class PlannedRepeat:
    key: RepeatKey
    seed_map: SeedMap
    repeat_id: str


@dataclass(frozen=True)
class RepeatPlan:
    """Fifty execution coordinates; they are not fifty independent datasets."""

    spec: RepeatSpec
    binding: SourceBinding
    outer_roles: tuple[OuterRoleManifest, ...]
    repeats: tuple[PlannedRepeat, ...]
    plan_digest: str

    def __post_init__(self) -> None:
        immutable_tuple(self.outer_roles, "outer_roles")
        immutable_tuple(self.repeats, "repeats")
        digest_field(self.plan_digest, "plan_digest")

    @cached_property
    def _repeats_by_key(self) -> dict[tuple[int, int], PlannedRepeat]:
        return {(item.key.outer_seed, item.key.inner_id): item for item in self.repeats}

    @cached_property
    def _roles_by_outer(self) -> dict[int, OuterRoleManifest]:
        return {manifest.outer_seed: manifest for manifest in self.outer_roles}

    def repeat(self, outer_seed: int, inner_id: int) -> PlannedRepeat:
        try:
            return self._repeats_by_key[(outer_seed, inner_id)]
        except KeyError:
            raise RepeatContractError("UNDECLARED_REPEAT", f"{outer_seed}/{inner_id}") from None

    def roles(self, outer_seed: int) -> OuterRoleManifest:
        try:
            return self._roles_by_outer[outer_seed]
        except KeyError:
            raise RepeatContractError("UNDECLARED_REPEAT", str(outer_seed)) from None

    @cached_property
    def group_universe(self) -> tuple[str, ...]:
        """Every evaluation group of every outer repeat, globally sorted once."""
        return tuple(sorted({
            group for manifest in self.outer_roles for group in manifest.evaluation_groups
        }))

    def group_counts(self, outer_seed: int) -> tuple[int, ...]:
        """Original evaluation rows per group; an absent group contributes zero."""
        counts = self.roles(outer_seed).group_row_counts
        return tuple(counts.get(group, 0) for group in self.group_universe)


@dataclass(frozen=True)
class PairContext:
    """Everything two paired strategies must share. Method identity is excluded."""

    dataset: str
    release: str
    protocol: str
    outer: int
    inner: int
    predictor: str
    scenario: str
    budget: int
    evaluation_ids: tuple[str, ...]
    group_map: tuple[tuple[str, str], ...]
    test_mask: str
    pool_mask: str
    acquisition_order: str
    acquired_prefix: tuple[str, ...]
    predictor_id: str
    seed_map: str
    source_binding: str

    def __post_init__(self) -> None:
        identifier(self.dataset, "dataset")
        identifier(self.release, "release")
        identifier(self.protocol, "protocol")
        declared_repeat(self.outer, self.inner)
        declared(self.predictor, PREDICTORS, "predictor")
        declared(self.scenario, SCENARIOS, "scenario")
        declared(strict_int(self.budget, "budget"), BUDGETS, "budget")
        evaluation = unique(identifier_tuple(self.evaluation_ids, "evaluation_ids"), "evaluation_ids")
        pairs = immutable_tuple(self.group_map, "group_map")
        if len(pairs) != len(evaluation):
            raise RepeatContractError("GROUP_MAP", "group_map")
        for row_id, pair in zip(evaluation, pairs):
            if type(pair) is not tuple or len(pair) != 2 or pair[0] != row_id:
                raise RepeatContractError("GROUP_MAP", "group_map")
            identifier(pair[1], "group_map")
        for name in ("test_mask", "pool_mask", "acquisition_order", "predictor_id",
                     "seed_map", "source_binding"):
            digest_field(getattr(self, name), name)
        prefix = unique(identifier_tuple(self.acquired_prefix, "acquired_prefix"), "acquired_prefix")
        if len(prefix) != self.budget:
            raise RepeatContractError("ACQUIRED_PREFIX", "acquired_prefix")
        if set(prefix).intersection(evaluation):
            raise RepeatContractError("ROLE_OVERLAP", "acquired_prefix")

    def differing_fields(self, other: PairContext) -> tuple[str, ...]:
        return tuple(
            name for name in self.__dataclass_fields__
            if getattr(self, name) != getattr(other, name)
        )

    def to_canonical(self) -> dict[str, Any]:
        value = {name: getattr(self, name) for name in self.__dataclass_fields__}
        value["evaluation_ids"] = list(self.evaluation_ids)
        value["group_map"] = [list(pair) for pair in self.group_map]
        value["acquired_prefix"] = list(self.acquired_prefix)
        return value

    @classmethod
    def from_canonical(cls, value: Any) -> PairContext:
        if not isinstance(value, dict) or set(value) != set(cls.__dataclass_fields__):
            raise RepeatContractError("RECORD_FIELDS", "pair context")
        fields = dict(value)
        try:
            for name in ("evaluation_ids", "acquired_prefix"):
                fields[name] = tuplify(fields[name])
            fields["group_map"] = tuple(tuple(pair) for pair in fields["group_map"])
        except TypeError:
            raise RepeatContractError("RECORD_FIELDS", "pair context") from None
        return cls(**fields)

    @cached_property
    def digest(self) -> str:
        return canonical_digest(self.to_canonical())


@dataclass(frozen=True)
class ProbabilityArray:
    """Two-column class probabilities of one requested strategy. No labels."""

    context: PairContext
    requested_method: str
    values: tuple[tuple[float, float], ...]

    def __post_init__(self) -> None:
        if type(self.context) is not PairContext:
            raise RepeatContractError("PAIR_SCHEMA", "context")
        declared(self.requested_method, METHODS, "requested_method")
        immutable_tuple(self.values, "values")


@dataclass(frozen=True)
class ValidatedPair:
    context: PairContext
    row_count: int
    target_digest: str
    source_digest: str


class ConditionSlot(NamedTuple):
    outer_seed: int
    inner_id: int
    predictor: str
    scenario: str
    budget: int
    method: str


@dataclass(frozen=True)
class TerminalCondition:
    """One terminal cell of the grid, keyed by its requested strategy."""

    condition_id: str
    repeat_id: str
    outer_seed: int
    inner_id: int
    predictor: str
    scenario: str
    budget: int
    requested_method: str
    resolved_method: str | None
    resolution_counts: tuple[tuple[str, int], ...]
    status: str
    metrics_available: bool
    qualification: str
    reasons: tuple[str, ...]
    fit_id: str | None

    def __post_init__(self) -> None:
        identifier(self.condition_id, "condition_id")
        digest_field(self.repeat_id, "repeat_id")
        strict_int(self.outer_seed, "outer_seed")
        strict_int(self.inner_id, "inner_id")
        identifier(self.predictor, "predictor")
        identifier(self.scenario, "scenario")
        strict_int(self.budget, "budget")
        identifier(self.requested_method, "requested_method")
        if self.resolved_method is not None:
            declared(self.resolved_method, METHODS, "resolved_method")
        validate_resolution_accounting(
            self.requested_method, self.resolved_method, self.resolution_counts, "resolution_counts"
        )
        strict_bool(self.metrics_available, "metrics_available")
        identifier_tuple(self.reasons, "reasons")
        if self.fit_id is not None:
            identifier(self.fit_id, "fit_id")
        if self.qualification not in QUALIFICATIONS:
            raise RepeatContractError("QUALIFICATION", repr(self.qualification))
        failed = self.status == "failed"
        if self.status not in ("completed", "failed"):
            raise RepeatContractError("TERMINAL_STATUS", repr(self.status))
        if failed != (self.qualification == "failed") or failed == self.metrics_available:
            raise RepeatContractError("TERMINAL_STATUS", "status/qualification/metrics disagree")
        if not failed and self.resolved_method is None:
            raise RepeatContractError("TERMINAL_STATUS", "completed condition has no resolution")
        if self.qualification != "qualified" and not self.reasons:
            raise RepeatContractError("TERMINAL_STATUS", "unavailable condition carries no reason")
        if failed and (self.resolved_method is not None or self.resolution_counts):
            raise RepeatContractError(
                "RESOLUTION_ACCOUNTING", "failed condition carries a resolution or counts"
            )

    @property
    def slot(self) -> ConditionSlot:
        return ConditionSlot(
            self.outer_seed, self.inner_id, self.predictor, self.scenario,
            self.budget, self.requested_method,
        )

    @property
    def row_count(self) -> int:
        """Rows accounted to a resolution; zero for a failed condition."""
        return sum(count for _, count in self.resolution_counts)

    @property
    def fallback_rows(self) -> int:
        return fallback_row_count(self.requested_method, self.resolution_counts)

    def to_canonical(self) -> dict[str, Any]:
        value = {name: getattr(self, name) for name in self.__dataclass_fields__}
        value["resolution_counts"] = [list(pair) for pair in self.resolution_counts]
        value["reasons"] = list(self.reasons)
        value["record_version"] = TERMINAL_CONDITION_RECORD_VERSION
        return value

    @classmethod
    def from_canonical(cls, value: Any) -> TerminalCondition:
        """Reopen a stored condition; every accounting rule is re-applied by the constructor."""
        fields = _stored_fields(value, cls, TERMINAL_CONDITION_RECORD_VERSION, "terminal condition")
        try:
            fields["resolution_counts"] = tuple(tuple(pair) for pair in fields["resolution_counts"])
            fields["reasons"] = tuplify(fields["reasons"])
        except TypeError:
            raise RepeatContractError("RECORD_FIELDS", "terminal condition") from None
        return cls(**fields)


@dataclass(frozen=True)
class MissingEvidence:
    """Typed unavailability. The estimate and interval are null by construction."""

    code: str
    missing: tuple = ()
    unavailable: tuple = ()
    reasons: tuple[str, ...] = ()
    invalid_draw_ids: tuple[int, ...] = ()
    primary_estimate: None = None
    interval: None = None

    def __post_init__(self) -> None:
        identifier(self.code, "code")
        for name in ("missing", "unavailable", "reasons", "invalid_draw_ids"):
            immutable_tuple(getattr(self, name), name)
        if self.primary_estimate is not None or self.interval is not None:
            raise RepeatContractError("MISSING_EVIDENCE_HAS_VALUE")


@dataclass(frozen=True)
class InventoryResult:
    expected_slots: int
    present_slots: int
    primary_pairs_required: int
    missing: tuple[ConditionSlot, ...]
    missing_primary: tuple[ConditionSlot, ...]
    terminal_failures: tuple[tuple[ConditionSlot, tuple[str, ...]], ...]
    unavailable_primary: tuple[tuple[ConditionSlot, str, tuple[str, ...]], ...]
    fallback_slots: tuple[ConditionSlot, ...]
    full_grid_complete: bool
    primary_ready: bool
    missing_evidence: MissingEvidence | None


@dataclass(frozen=True)
class PairedGroupLossCell:
    """Fabricated paired Brier-difference SUMS per evaluation group for one cell.

    In any future authorized run these sums are evaluator-private outcome
    information; this slice accepts fabricated values only.
    """

    context: PairContext
    target_condition_id: str
    source_condition_id: str
    group_ids: tuple[str, ...]
    n_by_group: tuple[int, ...]
    paired_loss_sum_by_group: tuple[float, ...] | None
    qualification: str
    reasons: tuple[str, ...]
    target_resolved_method: str | None
    source_resolved_method: str | None
    # Per-row resolution accounting of each side; a mixed fraction-binned condition keeps
    # its mixture here instead of hiding it behind the top-level method label.
    target_resolution_counts: tuple[tuple[str, int], ...]
    source_resolution_counts: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        if type(self.context) is not PairContext:
            raise RepeatContractError("PAIR_SCHEMA", "context")
        identifier(self.target_condition_id, "target_condition_id")
        identifier(self.source_condition_id, "source_condition_id")
        if self.target_condition_id == self.source_condition_id:
            raise RepeatContractError("DUPLICATE_VALUE", "condition_id")
        groups = identifier_tuple(self.group_ids, "group_ids")
        if not groups or list(groups) != sorted(set(groups)):
            raise RepeatContractError("GROUP_ORDER", "group_ids")
        counts = immutable_tuple(self.n_by_group, "n_by_group")
        if len(counts) != len(groups):
            raise RepeatContractError("GROUP_SHAPE", "n_by_group")
        for count in counts:
            if strict_int(count, "n_by_group") < 0:
                raise RepeatContractError("NEGATIVE_COUNT", "n_by_group")
        if self.qualification not in QUALIFICATIONS:
            raise RepeatContractError("QUALIFICATION", repr(self.qualification))
        identifier_tuple(self.reasons, "reasons")
        if self.qualification != "qualified" and not self.reasons:
            raise RepeatContractError("QUALIFICATION", "unavailable cell carries no reason")
        rows = sum(counts)
        for side, requested in (("target", PRIMARY_TARGET_METHOD), ("source", PRIMARY_SOURCE_METHOD)):
            resolved = getattr(self, f"{side}_resolved_method")
            if resolved is not None:
                declared(resolved, METHODS, f"{side}_resolved_method")
            total = validate_resolution_accounting(
                requested, resolved, getattr(self, f"{side}_resolution_counts"),
                f"{side}_resolution_counts",
            )
            if resolved is not None and total != rows:
                raise RepeatContractError(
                    "RESOLUTION_ACCOUNTING", f"{side} resolution counts do not sum to the cell rows"
                )
        sums = self.paired_loss_sum_by_group
        if sums is None:
            if self.qualification == "qualified":
                raise RepeatContractError("INVALID_GROUP_SUM", "qualified cell has no sums")
            return
        if self.qualification == "failed":
            raise RepeatContractError("INVALID_GROUP_SUM", "failed cell carries sums")
        if len(immutable_tuple(sums, "paired_loss_sum_by_group")) != len(groups):
            raise RepeatContractError("GROUP_SHAPE", "paired_loss_sum_by_group")
        for count, value in zip(counts, sums):
            # Each paired binary Brier difference lies in [-1, 1].
            if type(value) is not float or not math.isfinite(value) or abs(value) > count:
                raise RepeatContractError("INVALID_GROUP_SUM", "paired_loss_sum_by_group")
        if self.target_resolved_method is None or self.source_resolved_method is None:
            raise RepeatContractError("RESOLUTION_ACCOUNTING", "scored cell has an unresolved side")

    @property
    def key(self) -> tuple[int, int, str, str]:
        context = self.context
        return (context.outer, context.inner, context.predictor, context.scenario)

    @property
    def target_fallback_rows(self) -> int:
        return fallback_row_count(PRIMARY_TARGET_METHOD, self.target_resolution_counts)

    @property
    def source_fallback_rows(self) -> int:
        return fallback_row_count(PRIMARY_SOURCE_METHOD, self.source_resolution_counts)

    @property
    def has_fallback(self) -> bool:
        """True when any evaluation row resolved away from its requested primary method."""
        return self.target_fallback_rows > 0 or self.source_fallback_rows > 0

    def to_canonical(self) -> dict[str, Any]:
        value = {name: getattr(self, name) for name in self.__dataclass_fields__}
        value["context"] = self.context.to_canonical()
        for name in ("group_ids", "n_by_group", "reasons"):
            value[name] = list(getattr(self, name))
        if self.paired_loss_sum_by_group is not None:
            value["paired_loss_sum_by_group"] = list(self.paired_loss_sum_by_group)
        for name in ("target_resolution_counts", "source_resolution_counts"):
            value[name] = [list(pair) for pair in getattr(self, name)]
        value["record_version"] = PAIRED_CELL_RECORD_VERSION
        return value

    @classmethod
    def from_canonical(cls, value: Any) -> PairedGroupLossCell:
        """Reopen a stored cell. Older records lack resolution accounting and are refused."""
        fields = _stored_fields(value, cls, PAIRED_CELL_RECORD_VERSION, "paired cell")
        fields["context"] = PairContext.from_canonical(fields["context"])
        try:
            for name in ("group_ids", "n_by_group", "reasons"):
                fields[name] = tuplify(fields[name])
            if fields["paired_loss_sum_by_group"] is not None:
                fields["paired_loss_sum_by_group"] = tuplify(fields["paired_loss_sum_by_group"])
            for name in ("target_resolution_counts", "source_resolution_counts"):
                fields[name] = tuple(tuple(pair) for pair in fields[name])
        except TypeError:
            raise RepeatContractError("RECORD_FIELDS", "paired cell") from None
        return cls(**fields)
