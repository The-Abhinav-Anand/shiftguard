"""Pure planning of the fifty synthetic repeat identities."""

from __future__ import annotations

from shiftguard.repeats.models import (
    SYNTHETIC_EXPOSURE,
    OuterRoleManifest,
    PairContext,
    PlannedRepeat,
    RepeatContractError,
    RepeatKey,
    RepeatPlan,
    RepeatSpec,
    SourceBinding,
    canonical_digest,
    immutable_tuple,
)
from shiftguard.repeats.seeds import INNER_LEAVES, derive_repeat_seed_map


def plan_repeats(
    spec: RepeatSpec,
    binding: SourceBinding,
    roles: tuple[OuterRoleManifest, ...],
) -> RepeatPlan:
    """Bind spec, source, roles and seeds into one immutable plan. Loads nothing."""
    if type(spec) is not RepeatSpec or type(binding) is not SourceBinding:
        raise RepeatContractError("REPEAT_SCHEMA", "spec/binding")
    # This slice plans fabricated fixtures only; a real source needs a locked protocol.
    if binding.exposure_status != SYNTHETIC_EXPOSURE:
        raise RepeatContractError("SYNTHETIC_ONLY", binding.exposure_status)
    by_outer: dict[int, OuterRoleManifest] = {}
    for manifest in immutable_tuple(roles, "roles"):
        if type(manifest) is not OuterRoleManifest:
            raise RepeatContractError("REPEAT_SCHEMA", "roles")
        if manifest.outer_seed not in spec.outer_seeds:
            raise RepeatContractError("UNDECLARED_REPEAT", str(manifest.outer_seed))
        if manifest.outer_seed in by_outer:
            raise RepeatContractError("DUPLICATE_OUTER_ROLE", str(manifest.outer_seed))
        by_outer[manifest.outer_seed] = manifest
    for outer in spec.outer_seeds:
        if outer not in by_outer:
            raise RepeatContractError("MISSING_OUTER_ROLE", str(outer))
        if by_outer[outer].support_status != "supported":
            raise RepeatContractError("UNSUPPORTED_ROLE", str(outer))

    ordered_roles = tuple(by_outer[outer] for outer in spec.outer_seeds)
    repeats: list[PlannedRepeat] = []
    leaves: dict[int, tuple[int, int, str]] = {}
    for outer in spec.outer_seeds:
        for inner in spec.inner_ids:
            key = RepeatKey(outer, inner)
            seed_map = derive_repeat_seed_map(key, spec)
            for name, value in seed_map.seeds:
                if name not in INNER_LEAVES:
                    continue
                if value in leaves:
                    # Never rehash or redraw; a collision is surfaced for review.
                    raise RepeatContractError(
                        "SEED_COLLISION", f"{(outer, inner, name)} and {leaves[value]}"
                    )
                leaves[value] = (outer, inner, name)
            repeats.append(PlannedRepeat(key, seed_map, canonical_digest([
                "gate8-repeat-id-v1", spec.digest, binding.digest,
                by_outer[outer].digest, outer, inner, seed_map.digest,
            ])))
    return RepeatPlan(
        spec=spec,
        binding=binding,
        outer_roles=ordered_roles,
        repeats=tuple(repeats),
        plan_digest=canonical_digest([
            "gate8-repeat-plan-v1", spec.digest, binding.digest,
            [manifest.digest for manifest in ordered_roles],
            [repeat.repeat_id for repeat in repeats],
        ]),
    )


def ensure_planned(plan: RepeatPlan) -> RepeatPlan:
    """Reject a plan whose identities were not derived from its own contents."""
    if type(plan) is not RepeatPlan:
        raise RepeatContractError("REPEAT_SCHEMA", "plan")
    if plan != plan_repeats(plan.spec, plan.binding, plan.outer_roles):
        raise RepeatContractError("PLAN_INTEGRITY", plan.plan_digest)
    return plan


def pair_context_for(
    plan: RepeatPlan,
    key: RepeatKey,
    predictor: str,
    scenario: str,
    budget: int,
    *,
    test_mask: str,
    pool_mask: str,
    acquisition_order: str,
    acquired_prefix: tuple[str, ...],
    predictor_id: str,
) -> PairContext:
    """The shared context of one cell, with every plan-owned field taken from the plan."""
    manifest = plan.roles(key.outer_seed)
    return PairContext(
        dataset=plan.binding.dataset,
        release=plan.binding.release,
        protocol=plan.spec.protocol_version,
        outer=key.outer_seed,
        inner=key.inner_id,
        predictor=predictor,
        scenario=scenario,
        budget=budget,
        evaluation_ids=manifest.evaluation_ids,
        group_map=manifest.group_map,
        test_mask=test_mask,
        pool_mask=pool_mask,
        acquisition_order=acquisition_order,
        acquired_prefix=acquired_prefix,
        predictor_id=predictor_id,
        seed_map=plan.repeat(key.outer_seed, key.inner_id).seed_map.digest,
        source_binding=plan.binding.digest,
    )


def plan_owned_mismatch(plan: RepeatPlan, context: PairContext) -> tuple[str, ...]:
    """Names of plan-owned context fields that disagree with the plan."""
    manifest = plan.roles(context.outer)
    expected = {
        "dataset": plan.binding.dataset,
        "release": plan.binding.release,
        "protocol": plan.spec.protocol_version,
        "evaluation_ids": manifest.evaluation_ids,
        "group_map": manifest.group_map,
        "seed_map": plan.repeat(context.outer, context.inner).seed_map.digest,
        "source_binding": plan.binding.digest,
    }
    mismatched = [name for name, value in expected.items() if getattr(context, name) != value]
    if not set(context.acquired_prefix) <= set(manifest.target_pool_ids):
        mismatched.append("acquired_prefix")
    return tuple(mismatched)
