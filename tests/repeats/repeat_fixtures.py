"""Fabricated identifiers and group sums for the synthetic repeat slice.

Nothing here is read from a dataset, a model or an evaluator. Numbers are
arithmetic fixtures, not research findings.
"""

from __future__ import annotations

import hashlib

from shiftguard.repeats.models import (
    INNER_IDS,
    OUTER_SEEDS,
    PREDICTORS,
    PRIMARY_BUDGET,
    PRIMARY_SCENARIOS,
    PRIMARY_SOURCE_METHOD,
    PRIMARY_TARGET_METHOD,
    OuterRoleManifest,
    PairedGroupLossCell,
    RepeatKey,
    RepeatSpec,
    SourceBinding,
    canonical_digest,
)
from shiftguard.repeats.planning import pair_context_for, plan_repeats


GROUPS = ("synthetic-group-a", "synthetic-group-b")


def fake_digest(label: str) -> str:
    return hashlib.sha256(f"synthetic:{label}".encode("ascii")).hexdigest()


def synthetic_binding(**overrides) -> SourceBinding:
    values = {
        "dataset": "synthetic-fixture",
        "release": "fabricated-v1",
        "raw_sha256": fake_digest("raw"),
        "clean_sha256": fake_digest("clean"),
        "feature_schema_sha256": fake_digest("feature-schema"),
        "group_manifest_sha256": fake_digest("group-manifest"),
        "source_sha256": fake_digest("source"),
        "dependency_lock_sha256": fake_digest("dependency-lock"),
        "protocol_review_sha256": fake_digest("protocol-review"),
        "exposure_status": "synthetic_fabricated",
    }
    values.update(overrides)
    return SourceBinding(**values)


def synthetic_roles(outer_seed: int, group_sizes=(1, 3), **overrides) -> OuterRoleManifest:
    """One evaluation row per unit of group size; a zero size omits that group."""
    evaluation_ids, evaluation_groups = [], []
    for group, size in zip(GROUPS, group_sizes):
        for member in range(size):
            evaluation_ids.append(f"synthetic:eval:{group}:{member}")
            evaluation_groups.append(group)
    values = {
        "outer_seed": outer_seed,
        "split_profile": "synthetic_fixed_external",
        "train_ids": tuple(f"synthetic:train:{outer_seed}:{n}" for n in range(4)),
        "source_cal_ids": tuple(f"synthetic:source:{outer_seed}:{n}" for n in range(3)),
        "target_pool_ids": tuple(f"synthetic:pool:{outer_seed}:{n}" for n in range(200)),
        "evaluation_ids": tuple(evaluation_ids),
        "evaluation_groups": tuple(evaluation_groups),
        "evaluation_order_digest": canonical_digest(evaluation_ids),
    }
    values.update(overrides)
    return OuterRoleManifest(**values)


def synthetic_plan(group_sizes_by_outer=None):
    sizes = group_sizes_by_outer or {}
    roles = tuple(
        synthetic_roles(outer, sizes.get(outer, (1, 3))) for outer in OUTER_SEEDS
    )
    return plan_repeats(RepeatSpec(), synthetic_binding(), roles)


def primary_keys():
    return tuple(
        (outer, inner, predictor, scenario)
        for outer in OUTER_SEEDS
        for inner in INNER_IDS
        for predictor in PREDICTORS
        for scenario in PRIMARY_SCENARIOS
    )


def primary_context(plan, outer, inner, predictor, scenario):
    pool = plan.roles(outer).target_pool_ids
    return pair_context_for(
        plan,
        RepeatKey(outer, inner),
        predictor,
        scenario,
        PRIMARY_BUDGET,
        test_mask=fake_digest(f"test-mask:{outer}:{inner}:{scenario}"),
        pool_mask=fake_digest(f"pool-mask:{outer}:{inner}:{scenario}"),
        acquisition_order=fake_digest(f"acquisition:{outer}:{inner}"),
        acquired_prefix=pool[:PRIMARY_BUDGET],
        predictor_id=fake_digest(f"predictor:{outer}:{predictor}"),
    )


def primary_cell(plan, key, per_row_effect=None, sums=None, **overrides) -> PairedGroupLossCell:
    """Build one fabricated cell; ``sums`` is aligned with the plan's group universe."""
    outer, inner, predictor, scenario = key
    counts = plan.group_counts(outer)
    if sums is None:
        effect = 0.0 if per_row_effect is None else per_row_effect
        sums = tuple(count * effect for count in counts)
    values = {
        "context": primary_context(plan, outer, inner, predictor, scenario),
        "target_condition_id": fake_digest(f"target:{key}"),
        "source_condition_id": fake_digest(f"source:{key}"),
        "group_ids": plan.group_universe,
        "n_by_group": counts,
        "paired_loss_sum_by_group": tuple(sums),
        "qualification": "qualified",
        "reasons": (),
        "target_resolved_method": PRIMARY_TARGET_METHOD,
        "source_resolved_method": PRIMARY_SOURCE_METHOD,
    }
    values.update(overrides)
    # Fabricated resolution accounting follows the stated resolved methods: every evaluation row
    # of the outer repeat resolves to that one method, unless a test supplies its own counts.
    rows = sum(values["n_by_group"]) if type(values["n_by_group"]) is tuple else 0
    for side in ("target", "source"):
        resolved = values[f"{side}_resolved_method"]
        values.setdefault(f"{side}_resolution_counts", ((resolved, rows),) if resolved else ())
    return PairedGroupLossCell(**values)


def primary_cells(plan, sums_for=None) -> tuple[PairedGroupLossCell, ...]:
    """All 400 fabricated primary cells; ``sums_for(key, counts)`` supplies group sums."""
    cells = []
    for key in primary_keys():
        counts = plan.group_counts(key[0])
        sums = sums_for(key, counts) if sums_for is not None else None
        cells.append(primary_cell(plan, key, sums=sums))
    return tuple(cells)


def varied_sums(key, counts):
    """Deterministic fabricated sums that differ by cell and group, within their bounds."""
    values = []
    for index, count in enumerate(counts):
        fraction = int(fake_digest(f"varied:{key}:{index}")[:8], 16) / 0xFFFFFFFF
        values.append(count * (2.0 * fraction - 1.0))
    return tuple(values)


def packet_fixture_sums(_key, counts):
    """The reviewed packet's arithmetic fixture: counts [1, 3] with sums [.2, -.6]."""
    return tuple(value if count else 0.0 for value, count in zip((0.2, -0.6), counts))
