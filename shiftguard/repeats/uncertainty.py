"""Conditional evaluation-group bootstrap for the fabricated primary fixture.

One multiplicity is drawn per globally sorted evaluation group and reused for
every occurrence of that group across methods, cells, inner and outer repeats.
The interval is conditional on fits, seed schedule, masks and acquired
prefixes. It is not the blueprint's outer-first procedure; reconciling the two
needs a human scientific amendment that this implementation does not supply.
Draws are never discarded, redrawn or replaced.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from shiftguard.repeats.aggregation import (
    PreparedAggregate,
    derived_point_estimate,
    validate_prepared_aggregate,
)
from shiftguard.repeats.models import (
    MissingEvidence,
    RepeatContractError,
    RepeatPlan,
    identifier_tuple,
)


MODES = ("fixed_external", "bank_overlap_diagnostic")
DECLARED_DRAWS = 10_000
BOOTSTRAP_ROOT = 61001
BOOTSTRAP_NAMESPACE = (8, 1)
QUANTILES = (0.025, 0.975)
INTERPOLATION = "linear"
_CLAIM_SCOPE = {
    "fixed_external": (
        "synthetic fixture; conditional on fits, seed schedule, masks and acquired prefixes"
    ),
    "bank_overlap_diagnostic": (
        "synthetic fixture; development diagnostic without coverage, independence "
        "or confirmatory claim"
    ),
}


@dataclass(frozen=True)
class UncertaintySpec:
    """The reviewed procedure. Only the draw count may be reduced, and only visibly."""

    mode: str
    draws: int = DECLARED_DRAWS
    root: int = BOOTSTRAP_ROOT
    namespace: tuple[int, int] = BOOTSTRAP_NAMESPACE
    quantiles: tuple[float, float] = QUANTILES
    interpolation: str = INTERPOLATION

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise RepeatContractError("UNCERTAINTY_MODE", repr(self.mode))
        if type(self.draws) is not int or self.draws < 1:
            raise RepeatContractError("DRAW_COUNT", repr(self.draws))
        if (
            (self.root, self.namespace, self.quantiles, self.interpolation)
            != (BOOTSTRAP_ROOT, BOOTSTRAP_NAMESPACE, QUANTILES, INTERPOLATION)
            or type(self.root) is not int
        ):
            raise RepeatContractError("UNCERTAINTY_SPEC", "root/namespace/quantiles/interpolation")


@dataclass(frozen=True)
class DrawEstimate:
    """One draw; ``value`` is None when a required outer repeat had no row mass."""

    draw_id: int
    value: float | None


@dataclass(frozen=True)
class IntervalResult:
    mode: str
    lower: float
    upper: float
    draws: int
    point_estimate: float
    group_count: int
    degenerate: bool
    declared_procedure: bool
    coverage_claim: bool
    hypothesis_decision: None
    claim_scope: str
    plan_digest: str
    synthetic: bool


def _sorted_groups(group_ids: tuple[str, ...]) -> tuple[str, ...]:
    groups = identifier_tuple(group_ids, "group_ids")
    if not groups or list(groups) != sorted(set(groups)):
        raise RepeatContractError("GROUP_ORDER", "group_ids")
    return groups


def _weights(group_count: int, draw_id: int, spec: UncertaintySpec) -> np.ndarray:
    # Each draw owns a stable namespace, so replay and resume need no generator state.
    sequence = np.random.SeedSequence([spec.root, *spec.namespace, draw_id])
    generator = np.random.Generator(np.random.PCG64(sequence))
    return np.bincount(generator.integers(0, group_count, size=group_count), minlength=group_count)


def group_multiplicities(
    group_ids: tuple[str, ...], draw_id: int, spec: UncertaintySpec
) -> tuple[int, ...]:
    """The shared cluster multiplicities of one predeclared draw."""
    if type(spec) is not UncertaintySpec:
        raise RepeatContractError("REPEAT_SCHEMA", "spec")
    groups = _sorted_groups(group_ids)
    if type(draw_id) is not int or not 0 <= draw_id < spec.draws:
        raise RepeatContractError("DRAW_SCHEMA", repr(draw_id))
    return tuple(int(value) for value in _weights(len(groups), draw_id, spec))


def _matrices(prepared: PreparedAggregate, plan: RepeatPlan) -> tuple[np.ndarray, np.ndarray]:
    # Every consumer revalidates against the plan: the object is detachable and replaceable.
    # After validation all counts are bounded Python integers, so int64 conversion is exact.
    validate_prepared_aggregate(prepared, plan)
    return (
        np.asarray(prepared.counts, dtype=np.int64),
        np.asarray(prepared.collapsed_sums, dtype=np.float64),
    )


def _require_fixed_cohort(prepared: PreparedAggregate, counts: np.ndarray, spec: UncertaintySpec) -> None:
    """Fixed-external mode: one cohort, i.e. the same row-to-group membership in every outer
    repeat, not merely equal group totals. Row order within a cohort is irrelevant. The
    Bank overlap diagnostic keeps its differing memberships and its nonconfirmatory label."""
    if spec.mode != "fixed_external":
        return
    cohorts = {tuple(sorted(pairs)) for pairs in prepared.membership_by_outer}
    if len(cohorts) != 1 or not (counts == counts[0]).all():
        raise RepeatContractError("VARYING_EXTERNAL_EVALUATION_MEMBERSHIP")


def _draw_value(counts: np.ndarray, sums: np.ndarray, weights: np.ndarray) -> float | None:
    denominators = counts @ weights
    if (denominators == 0).any():
        return None
    return float(np.mean((sums @ weights) / denominators))


def draw_estimates(
    prepared: PreparedAggregate,
    spec: UncertaintySpec,
    start: int,
    stop: int,
    *,
    plan: RepeatPlan,
) -> tuple[DrawEstimate, ...]:
    """Estimates of draws ``start..stop-1``; any chunking reproduces the full pass."""
    if type(spec) is not UncertaintySpec:
        raise RepeatContractError("REPEAT_SCHEMA", "spec")
    counts, sums = _matrices(prepared, plan)
    _require_fixed_cohort(prepared, counts, spec)
    if type(start) is not int or type(stop) is not int or not 0 <= start <= stop <= spec.draws:
        raise RepeatContractError("DRAW_SCHEMA", f"{start!r}..{stop!r}")
    group_count = counts.shape[1]
    return tuple(
        DrawEstimate(draw_id, _draw_value(counts, sums, _weights(group_count, draw_id, spec)))
        for draw_id in range(start, stop)
    )


def paired_group_interval(
    prepared: PreparedAggregate | MissingEvidence,
    spec: UncertaintySpec,
    *,
    plan: RepeatPlan,
) -> IntervalResult | MissingEvidence:
    """Percentile interval over the predeclared draws, or typed unavailability.

    Missing evidence passes through untouched; invalid evidence is a typed error.
    """
    if isinstance(prepared, MissingEvidence):
        return prepared
    if type(spec) is not UncertaintySpec:
        raise RepeatContractError("REPEAT_SCHEMA", "spec")
    counts, sums = _matrices(prepared, plan)
    _require_fixed_cohort(prepared, counts, spec)
    if counts.shape[1] < 2 or (counts.sum(axis=0) == 0).any():
        return MissingEvidence(
            code="INSUFFICIENT_GROUPS",
            reasons=("fewer than two evaluation groups carry row mass",),
        )
    group_count = counts.shape[1]
    values, invalid = [], []
    # Only one scalar per draw is retained; no draws-by-cells tensor is ever built.
    for draw_id in range(spec.draws):
        value = _draw_value(counts, sums, _weights(group_count, draw_id, spec))
        if value is None:
            invalid.append(draw_id)
        else:
            values.append(value)
    if invalid:
        return MissingEvidence(
            code="INVALID_DRAWS",
            invalid_draw_ids=tuple(invalid),
            reasons=("a draw left a required outer repeat without evaluated row mass",),
        )
    lower, upper = (
        float(value) for value in np.quantile(values, spec.quantiles, method=spec.interpolation)
    )
    return IntervalResult(
        mode=spec.mode,
        lower=lower,
        upper=upper,
        draws=spec.draws,
        point_estimate=derived_point_estimate(prepared.counts, prepared.collapsed_sums),
        group_count=group_count,
        degenerate=lower == upper,
        declared_procedure=spec.draws == DECLARED_DRAWS,
        coverage_claim=False,
        hypothesis_decision=None,
        claim_scope=_CLAIM_SCOPE[spec.mode],
        plan_digest=prepared.plan_digest,
        synthetic=True,
    )
