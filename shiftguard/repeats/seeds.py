"""Seed derivation ``gate8-nested-v1`` for the reviewed 5x10 repeat design.

Ported from the reviewed P1 reference. Seeds are execution coordinates: the
outer split/model streams are shared by every inner repeat of an outer seed,
while mask, acquisition and source-remask streams change with the inner ID.
The accepted development seed 31001 and its legacy bundle are not touched.
"""

from __future__ import annotations

import numpy as np

from shiftguard.repeats.models import (
    RepeatContractError,
    RepeatKey,
    RepeatSpec,
    SeedMap,
    canonical_digest,
)


OUTER_STREAMS = ("split", "model")
INNER_STREAMS = ("mask", "acquisition", "source_remask")
MASK_STREAMS = ("pool_block", "test_block", "pool_mcar", "test_mcar")
SOURCE_REMASK_STREAMS = ("source_mcar", "source_block")
# Leaves that must never coincide across execution coordinates.
INNER_LEAVES = MASK_STREAMS + ("acquisition",) + SOURCE_REMASK_STREAMS
_UINT32_MAX = 2**32 - 1


def _u32(sequence: np.random.SeedSequence) -> int:
    return int(sequence.generate_state(1, dtype=np.uint32)[0])


def derive_repeat_seed_map(key: RepeatKey, spec: RepeatSpec) -> SeedMap:
    """Pure: the same key always yields the same map, whatever the request order."""
    if type(key) is not RepeatKey or type(spec) is not RepeatSpec:
        raise RepeatContractError("REPEAT_SCHEMA", "key/spec")
    if key.outer_seed not in spec.outer_seeds or key.inner_id not in spec.inner_ids:
        raise RepeatContractError("UNDECLARED_REPEAT", f"{key.outer_seed}/{key.inner_id}")
    if np.__version__ != spec.numpy_version:
        raise RepeatContractError("NUMPY_VERSION", np.__version__)

    outer = np.random.SeedSequence(key.outer_seed).spawn(len(OUTER_STREAMS))
    inner = np.random.SeedSequence([key.outer_seed, key.inner_id]).spawn(len(INNER_STREAMS))
    seeds = dict(zip(OUTER_STREAMS, map(_u32, outer)))
    seeds.update(zip(INNER_STREAMS, map(_u32, inner)))
    # The inherited three-stage row split consumes split, split+1 and split+2.
    if seeds["split"] > _UINT32_MAX - 2:
        raise RepeatContractError("SPLIT_INCREMENT_OVERFLOW", str(key.outer_seed))
    seeds["split_stage_2"] = seeds["split"] + 1
    seeds["split_stage_3"] = seeds["split"] + 2
    models = np.random.SeedSequence(seeds["model"]).spawn(len(spec.predictors))
    seeds.update((f"model_{name}", _u32(child)) for name, child in zip(spec.predictors, models))
    masks = np.random.SeedSequence(seeds["mask"]).spawn(len(MASK_STREAMS))
    seeds.update(zip(MASK_STREAMS, map(_u32, masks)))
    children = np.random.Generator(np.random.PCG64(seeds["source_remask"])).integers(
        0, 1_000_000, size=len(SOURCE_REMASK_STREAMS)
    )
    seeds.update(zip(SOURCE_REMASK_STREAMS, (int(value) for value in children)))
    return SeedMap(
        algorithm_version=spec.seed_algorithm_version,
        outer_seed=key.outer_seed,
        inner_id=key.inner_id,
        numpy_version=spec.numpy_version,
        seeds=tuple(sorted(seeds.items())),
    )


def seed_plan_digest(spec: RepeatSpec) -> str:
    """Digest of all fifty maps in declared order, as bound by the reviewed packet."""
    return canonical_digest([
        [outer, inner, [list(pair) for pair in derive_repeat_seed_map(
            RepeatKey(outer, inner), spec
        ).seeds]]
        for outer in spec.outer_seeds
        for inner in spec.inner_ids
    ])
