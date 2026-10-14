"""Pure reducer for the single planned primary contrast.

Contrast: target_temperature minus source_fraction_binned_temperature at budget
50, binary Brier MSE. Original row mass is kept within each cell; the eight
shifted cells, ten inner repeats and five outer repeats then weigh equally.
Inputs are fabricated paired group sums. No labels, loaders or evaluators.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import statistics

from shiftguard.repeats.models import (
    OUTER_SEEDS,
    PRIMARY_BUDGET,
    PRIMARY_SCENARIOS,
    PRIMARY_SOURCE_METHOD,
    PRIMARY_TARGET_METHOD,
    SYNTHETIC_CLAIM_SCOPE,
    MissingEvidence,
    PairedGroupLossCell,
    RepeatContractError,
    RepeatPlan,
    identifier,
    identifier_tuple,
    immutable_tuple,
    strict_int,
)
from shiftguard.repeats.planning import ensure_planned, plan_owned_mismatch


PrimaryKey = tuple[int, int, str, str]


@dataclass(frozen=True)
class PrimarySummary:
    """Point summary and realized split/seed sensitivity of a fabricated fixture.

    The spreads are sensitivity diagnostics. They are never divided by the
    number of repeats: fifty executions are not fifty independent datasets.
    """

    theta: float
    outer_values: tuple[float, ...]
    inner_values: tuple[tuple[float, ...], ...]
    inner_sd_by_outer: tuple[float, ...]
    outer_sd: float
    cell_count: int
    rows_by_outer: tuple[int, ...]
    groups_by_outer: tuple[int, ...]
    unique_evaluation_rows: int
    unique_groups: int
    total_row_appearances: int
    fallback_cells: int
    execution_coordinates: int
    source_releases: int
    seed_count_is_sample_size: bool
    contrast: tuple[str, str]
    budget: int
    metric: str
    direction: str
    plan_digest: str
    claim_scope: str
    synthetic: bool


@dataclass(frozen=True)
class PreparedAggregate:
    """Group sums collapsed once over inner repeats and cells, per outer repeat.

    ``collapsed_sums[o][g]`` is the mean over that outer's 80 cells of the
    paired sums of group ``g``. Row counts are constant within an outer, so a
    group-weighted estimate needs only these and ``counts``.

    ``membership_by_outer[o]`` keeps the ordered ``(row_id, group_id)`` pairs of that
    outer's evaluation rows, so the counts can be recomputed and fixed-external use can
    compare actual cohorts. The object is detachable and replaceable: every consumer
    must call ``validate_prepared_aggregate`` with the plan before using any value, and
    ``point_estimate`` is only a stored claim that validation re-derives and compares.
    """

    plan_digest: str
    group_ids: tuple[str, ...]
    counts: tuple[tuple[int, ...], ...]
    membership_by_outer: tuple[tuple[tuple[str, str], ...], ...]
    collapsed_sums: tuple[tuple[float, ...], ...]
    point_estimate: float
    claim_scope: str
    synthetic: bool


def primary_keys(plan: RepeatPlan) -> tuple[PrimaryKey, ...]:
    return tuple(
        (outer, inner, predictor, scenario)
        for outer in plan.spec.outer_seeds
        for inner in plan.spec.inner_ids
        for predictor in plan.spec.predictors
        for scenario in PRIMARY_SCENARIOS
    )


def _single(values: set, key: tuple) -> None:
    if len(values) > 1:
        raise RepeatContractError("SHARED_CONTEXT_MISMATCH", repr(key))


def _collect(
    plan: RepeatPlan, pairs: tuple[PairedGroupLossCell, ...]
) -> dict[PrimaryKey, PairedGroupLossCell] | MissingEvidence:
    ensure_planned(plan)
    cells: dict[PrimaryKey, PairedGroupLossCell] = {}
    for cell in immutable_tuple(pairs, "pairs"):
        if type(cell) is not PairedGroupLossCell:
            raise RepeatContractError("REPEAT_SCHEMA", "pairs")
        context = cell.context
        if context.budget != PRIMARY_BUDGET or context.scenario not in PRIMARY_SCENARIOS:
            raise RepeatContractError("UNEXPECTED_PRIMARY_CELL", repr(cell.key))
        if cell.key in cells:
            raise RepeatContractError("DUPLICATE_PRIMARY_CELL", repr(cell.key))
        mismatch = plan_owned_mismatch(plan, context)
        if mismatch:
            raise RepeatContractError("PAIR_CONTEXT_MISMATCH", f"{cell.key}: {', '.join(mismatch)}")
        if cell.group_ids != plan.group_universe:
            raise RepeatContractError("GROUP_UNIVERSE_MISMATCH", repr(cell.key))
        if cell.n_by_group != plan.group_counts(context.outer):
            raise RepeatContractError("GROUP_COUNT_MISMATCH", repr(cell.key))
        cells[cell.key] = cell

    # Paired comparisons share masks and acquisition; a predictor is fitted once per outer.
    acquisition: dict[tuple, set] = {}
    masks: dict[tuple, set] = {}
    predictors: dict[tuple, set] = {}
    for (outer, inner, predictor, scenario), cell in cells.items():
        context = cell.context
        acquisition.setdefault((outer, inner), set()).add(
            (context.acquisition_order, context.acquired_prefix)
        )
        masks.setdefault((outer, inner, scenario), set()).add(
            (context.test_mask, context.pool_mask)
        )
        predictors.setdefault((outer, predictor), set()).add(context.predictor_id)
    for shared in (acquisition, masks, predictors):
        for key, values in shared.items():
            _single(values, key)

    # Any absent or unavailable required pair nulls the primary; survivors are never reweighted.
    missing, unavailable = [], []
    for key in primary_keys(plan):
        cell = cells.get(key)
        if cell is None:
            missing.append(key)
        elif cell.qualification != "qualified":
            unavailable.append((key, cell.qualification, cell.reasons))
    if missing or unavailable:
        return MissingEvidence(
            code="PRIMARY_EVIDENCE_UNAVAILABLE",
            missing=tuple(missing),
            unavailable=tuple(unavailable),
            reasons=tuple(sorted({reason for _, _, reasons in unavailable for reason in reasons})),
        )
    return cells


def _mean(values: list[float]) -> float:
    return math.fsum(values) / len(values)


def aggregate_primary(
    plan: RepeatPlan,
    pairs: tuple[PairedGroupLossCell, ...],
) -> PrimarySummary | MissingEvidence:
    """Reduce the 400 required primary cells; input order never changes the result."""
    cells = _collect(plan, pairs)
    if isinstance(cells, MissingEvidence):
        return cells
    spec = plan.spec
    inner_values: list[tuple[float, ...]] = []
    for outer in spec.outer_seeds:
        row = []
        for inner in spec.inner_ids:
            deltas = []
            for predictor in spec.predictors:
                for scenario in PRIMARY_SCENARIOS:
                    cell = cells[(outer, inner, predictor, scenario)]
                    deltas.append(
                        math.fsum(cell.paired_loss_sum_by_group) / sum(cell.n_by_group)
                    )
            row.append(_mean(deltas))
        inner_values.append(tuple(row))
    outer_values = tuple(_mean(list(row)) for row in inner_values)
    counts = tuple(plan.group_counts(outer) for outer in spec.outer_seeds)
    rows_by_outer = tuple(sum(row) for row in counts)
    return PrimarySummary(
        theta=_mean(list(outer_values)),
        outer_values=outer_values,
        inner_values=tuple(inner_values),
        inner_sd_by_outer=tuple(statistics.stdev(row) for row in inner_values),
        outer_sd=statistics.stdev(outer_values),
        cell_count=len(cells),
        rows_by_outer=rows_by_outer,
        groups_by_outer=tuple(sum(1 for count in row if count) for row in counts),
        unique_evaluation_rows=len({
            row_id for manifest in plan.outer_roles for row_id in manifest.evaluation_ids
        }),
        unique_groups=len(plan.group_universe),
        total_row_appearances=sum(rows_by_outer),
        # Any row resolving away from its requested method counts, also inside a mixed binned map.
        fallback_cells=sum(1 for cell in cells.values() if cell.has_fallback),
        execution_coordinates=len(plan.repeats),
        source_releases=1,
        seed_count_is_sample_size=False,
        contrast=(PRIMARY_TARGET_METHOD, PRIMARY_SOURCE_METHOD),
        budget=PRIMARY_BUDGET,
        metric="binary_brier_mse",
        direction="target_minus_source",
        plan_digest=plan.plan_digest,
        claim_scope=SYNTHETIC_CLAIM_SCOPE,
        synthetic=True,
    )


def prepare_group_sums(
    plan: RepeatPlan,
    pairs: tuple[PairedGroupLossCell, ...],
) -> PreparedAggregate | MissingEvidence:
    """Collapse the per-cell group sums once for the conditional group interval."""
    cells = _collect(plan, pairs)
    if isinstance(cells, MissingEvidence):
        return cells
    spec = plan.spec
    groups = range(len(plan.group_universe))
    collapsed = []
    for outer in spec.outer_seeds:
        outer_cells = [
            cells[(outer, inner, predictor, scenario)]
            for inner in spec.inner_ids
            for predictor in spec.predictors
            for scenario in PRIMARY_SCENARIOS
        ]
        collapsed.append(tuple(
            math.fsum(cell.paired_loss_sum_by_group[group] for cell in outer_cells)
            / len(outer_cells)
            for group in groups
        ))
    counts = tuple(plan.group_counts(outer) for outer in spec.outer_seeds)
    sums = tuple(collapsed)
    prepared = PreparedAggregate(
        plan_digest=plan.plan_digest,
        group_ids=plan.group_universe,
        counts=counts,
        membership_by_outer=tuple(plan.roles(outer).group_map for outer in spec.outer_seeds),
        collapsed_sums=sums,
        point_estimate=derived_point_estimate(counts, sums),
        claim_scope=SYNTHETIC_CLAIM_SCOPE,
        synthetic=True,
    )
    validate_prepared_aggregate(prepared, plan)
    return prepared


# Per-outer row mass and caller weights stay far below int64 and exactly representable as
# float64 (2**53); with at most 2**62 // groups mass per outer, the bootstrap's integer
# products (multiplicities sum to the group count) cannot overflow either.
_MAX_EXACT = 2**53


def _count_bound(group_count: int) -> int:
    return min(_MAX_EXACT, (2**62) // max(group_count, 1))


def _weighted_estimate(
    counts: tuple[tuple[int, ...], ...],
    sums: tuple[tuple[float, ...], ...],
    weights: tuple[int, ...],
) -> float | None:
    """Exact-integer denominators; the estimate is None if any outer has no weighted row mass."""
    outers = []
    for count_row, sum_row in zip(counts, sums):
        denominator = sum(weight * count for weight, count in zip(weights, count_row))
        if denominator == 0:
            return None
        outers.append(
            math.fsum(weight * value for weight, value in zip(weights, sum_row)) / denominator
        )
    return _mean(outers)


def derived_point_estimate(
    counts: tuple[tuple[int, ...], ...], sums: tuple[tuple[float, ...], ...]
) -> float:
    """Unit-multiplicity estimate from counts and sums; callers validate them first."""
    value = _weighted_estimate(counts, sums, (1,) * len(counts[0]))
    if value is None:
        raise RepeatContractError("ZERO_ROW_MASS", "an outer repeat has no evaluation rows")
    return value


def validate_prepared_aggregate(prepared: PreparedAggregate, plan: RepeatPlan) -> None:
    """Reject any aggregate that is not exactly what ``plan`` and its own membership imply.

    Nothing is clipped, widened, dropped or renormalised: an impossible value is an error.
    """
    ensure_planned(plan)
    if type(prepared) is not PreparedAggregate:
        raise RepeatContractError("REPEAT_SCHEMA", "prepared")
    # This slice handles fabricated sums only; real paired sums are evaluator-private.
    if prepared.synthetic is not True:
        raise RepeatContractError("SYNTHETIC_ONLY", "prepared")
    groups = identifier_tuple(prepared.group_ids, "group_ids")
    if not groups or list(groups) != sorted(set(groups)):
        raise RepeatContractError("GROUP_ORDER", "group_ids")
    counts = immutable_tuple(prepared.counts, "counts")
    sums = immutable_tuple(prepared.collapsed_sums, "collapsed_sums")
    membership = immutable_tuple(prepared.membership_by_outer, "membership_by_outer")
    if not (len(counts) == len(sums) == len(membership) == len(OUTER_SEEDS)):
        raise RepeatContractError("PREPARED_SHAPE", "outer repeats")
    for count_row, sum_row in zip(counts, sums):
        if (
            len(immutable_tuple(count_row, "counts")) != len(groups)
            or len(immutable_tuple(sum_row, "collapsed_sums")) != len(groups)
        ):
            raise RepeatContractError("PREPARED_SHAPE", "groups")
    bound = _count_bound(len(groups))
    for count_row, sum_row in zip(counts, sums):
        # Counts are checked as Python integers before any NumPy conversion or product.
        for count in count_row:
            if strict_int(count, "counts") < 0:
                raise RepeatContractError("NEGATIVE_COUNT", "counts")
        if sum(count_row) > bound:
            raise RepeatContractError("COUNT_OVERFLOW", "counts")
        for value in sum_row:
            if type(value) is not float or not math.isfinite(value):
                raise RepeatContractError("INVALID_GROUP_SUM", "collapsed_sums")

    if prepared.plan_digest != plan.plan_digest:
        raise RepeatContractError("PLAN_DIGEST_MISMATCH", "prepared")
    if prepared.claim_scope != SYNTHETIC_CLAIM_SCOPE:
        raise RepeatContractError("CLAIM_SCOPE", "prepared")
    if groups != plan.group_universe:
        raise RepeatContractError("GROUP_UNIVERSE_MISMATCH", "prepared")

    for outer, count_row, sum_row, pairs in zip(plan.spec.outer_seeds, counts, sums, membership):
        for pair in immutable_tuple(pairs, "membership_by_outer"):
            if type(pair) is not tuple or len(pair) != 2:
                raise RepeatContractError("MEMBERSHIP_SCHEMA", str(outer))
            identifier(pair[0], "membership_by_outer")
            identifier(pair[1], "membership_by_outer")
        if pairs != plan.roles(outer).group_map:
            raise RepeatContractError("MEMBERSHIP_MISMATCH", str(outer))
        tally = {group: 0 for group in groups}
        for _, group in pairs:
            if group not in tally:
                raise RepeatContractError("MEMBERSHIP_MISMATCH", str(outer))
            tally[group] += 1
        recomputed = tuple(tally[group] for group in groups)
        if recomputed != count_row or recomputed != plan.group_counts(outer):
            raise RepeatContractError("GROUP_COUNT_MISMATCH", str(outer))
        if sum(count_row) <= 0:
            raise RepeatContractError("ZERO_ROW_MASS", str(outer))
        for count, value in zip(count_row, sum_row):
            # A paired binary Brier difference per row lies in [-1, 1]; zero rows give zero.
            if abs(value) > count:
                raise RepeatContractError("INVALID_GROUP_SUM", "outside signed row-count bounds")

    derived = derived_point_estimate(counts, sums)
    if type(prepared.point_estimate) is not float or prepared.point_estimate != derived:
        raise RepeatContractError("POINT_ESTIMATE_MISMATCH", "prepared")


def weighted_estimate(
    prepared: PreparedAggregate, multiplicities: tuple[int, ...], *, plan: RepeatPlan
) -> float | None:
    """Estimate with one shared multiplicity per group; None if any outer has no row mass.

    A multiplicity scales both the group's loss sums and its member-row count.
    """
    validate_prepared_aggregate(prepared, plan)
    if len(multiplicities) != len(prepared.group_ids):
        raise RepeatContractError("MULTIPLICITY_SCHEMA", "length")
    for weight in multiplicities:
        if type(weight) is not int or weight < 0:
            raise RepeatContractError("MULTIPLICITY_SCHEMA", "value")
        if weight > _MAX_EXACT:
            raise RepeatContractError("MULTIPLICITY_SCHEMA", "overflow")
    return _weighted_estimate(prepared.counts, prepared.collapsed_sums, tuple(multiplicities))
