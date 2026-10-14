from __future__ import annotations

import dataclasses
import subprocess
import sys

import pytest

from repeat_fixtures import synthetic_binding, synthetic_plan, synthetic_roles
from shiftguard.repeats.models import (
    INNER_IDS,
    OUTER_SEEDS,
    RepeatContractError,
    RepeatKey,
    RepeatSpec,
)
from shiftguard.repeats.planning import plan_repeats
from shiftguard.repeats.seeds import derive_repeat_seed_map, seed_plan_digest


GOLDEN_SEED_PLAN_DIGEST = "68900ea10536435e183f1f57d47154281f7c32db34a5f837b369330693bbffee"
PACKET_VECTOR = {
    "acquisition": 2826979832,
    "mask": 1077475791,
    "model": 3090476256,
    "model_logistic_regression": 1581660951,
    "model_random_forest": 3510111400,
    "pool_block": 567367985,
    "pool_mcar": 2568490269,
    "source_block": 117425,
    "source_mcar": 206066,
    "source_remask": 4235766874,
    "split": 1613160217,
    "split_stage_2": 1613160218,
    "split_stage_3": 1613160219,
    "test_block": 3998268314,
    "test_mcar": 1901172132,
}
INNER_LEAVES = (
    "pool_block", "test_block", "pool_mcar", "test_mcar",
    "acquisition", "source_mcar", "source_block",
)


def _code(call) -> str:
    with pytest.raises(RepeatContractError) as raised:
        call()
    return raised.value.code


def _all_maps():
    spec = RepeatSpec()
    return {
        (outer, inner): derive_repeat_seed_map(RepeatKey(outer, inner), spec)
        for outer in OUTER_SEEDS
        for inner in INNER_IDS
    }


def test_fifty_seed_maps_match_the_reviewed_golden_digest_and_packet_vector():
    spec = RepeatSpec()
    assert seed_plan_digest(spec) == GOLDEN_SEED_PLAN_DIGEST
    seed_map = derive_repeat_seed_map(RepeatKey(41001, 51001), spec)
    assert dict(seed_map.seeds) == PACKET_VECTOR
    assert seed_map.seeds == tuple(sorted(PACKET_VECTOR.items()))
    assert (seed_map.algorithm_version, seed_map.numpy_version) == ("gate8-nested-v1", "2.5.3")


def test_outer_streams_are_shared_and_inner_streams_are_distinct():
    maps = {key: dict(value.seeds) for key, value in _all_maps().items()}
    assert len(maps) == 50
    outer_names = ("split", "model", "model_logistic_regression", "model_random_forest")
    for outer in OUTER_SEEDS:
        for name in outer_names:
            assert len({maps[(outer, inner)][name] for inner in INNER_IDS}) == 1
    assert len({maps[(outer, INNER_IDS[0])]["split"] for outer in OUTER_SEEDS}) == 5
    leaves = [maps[key][name] for key in maps for name in INNER_LEAVES]
    assert len(set(leaves)) == len(leaves) == 350
    for name in ("mask", "acquisition", "source_remask"):
        assert len({maps[key][name] for key in maps}) == 50
    assert all(
        seeds["model_logistic_regression"] != seeds["model_random_forest"]
        for seeds in maps.values()
    )


def test_seed_derivation_replays_independently_of_request_order():
    spec = RepeatSpec()
    forward = [
        derive_repeat_seed_map(RepeatKey(outer, inner), spec)
        for outer in OUTER_SEEDS for inner in INNER_IDS
    ]
    backward = [
        derive_repeat_seed_map(RepeatKey(outer, inner), spec)
        for outer in reversed(OUTER_SEEDS) for inner in reversed(INNER_IDS)
    ]
    assert forward == list(reversed(backward))


@pytest.mark.parametrize("outer, inner, code", [
    (True, 51001, "STRICT_INTEGER"),
    (41001.0, 51001, "STRICT_INTEGER"),
    (41001, 51001.0, "STRICT_INTEGER"),
    ("41001", 51001, "STRICT_INTEGER"),
    (41006, 51001, "UNDECLARED_REPEAT"),
    (41001, 51011, "UNDECLARED_REPEAT"),
    (31001, 51001, "UNDECLARED_REPEAT"),
])
def test_boolean_float_and_undeclared_seeds_are_rejected(outer, inner, code):
    assert _code(lambda: derive_repeat_seed_map(RepeatKey(outer, inner), RepeatSpec())) == code


@pytest.mark.parametrize("change, code", [
    ({"outer_seeds": (41001,)}, "ALTERED_GRID"),
    ({"outer_seeds": (41001, 41002, 41003, 41004, 41006)}, "ALTERED_GRID"),
    ({"outer_seeds": (41001, 41001, 41003, 41004, 41005)}, "DUPLICATE_VALUE"),
    ({"outer_seeds": ()}, "EMPTY_VALUE"),
    ({"outer_seeds": (41001.0, 41002, 41003, 41004, 41005)}, "STRICT_INTEGER"),
    ({"inner_ids": (True,) + INNER_IDS[1:]}, "STRICT_INTEGER"),
    ({"inner_ids": INNER_IDS[:9]}, "ALTERED_GRID"),
    ({"outer_seeds": list(OUTER_SEEDS)}, "IMMUTABLE_TUPLE"),
    ({"budgets": (0, 25, 50, 100)}, "ALTERED_GRID"),
    ({"budgets": (0, 25, 50.0, 100, 200)}, "STRICT_INTEGER"),
    ({"methods": ("raw",)}, "ALTERED_GRID"),
    ({"scenarios": ("baseline", "history_block_0_50")}, "ALTERED_GRID"),
    ({"predictors": ("logistic_regression",)}, "ALTERED_GRID"),
    ({"confirmatory_dispatch_permitted": True}, "CONFIRMATORY_DISPATCH_FORBIDDEN"),
    ({"execution_mode": "confirmatory"}, "EXECUTION_MODE"),
    ({"schema_version": "gate8-repeat-engineering-v2"}, "SCHEMA_VERSION"),
    ({"protocol_version": "shiftguard.research.protocol-draft.v0.4"}, "PROTOCOL_VERSION"),
    ({"seed_algorithm_version": "gate8-nested-v2"}, "SEED_ALGORITHM_VERSION"),
    ({"numpy_version": "2.5.2"}, "NUMPY_VERSION"),
])
def test_repeat_spec_rejects_every_alteration_of_the_declared_design(change, code):
    assert _code(lambda: RepeatSpec(**change)) == code


def test_plan_has_fifty_unique_repeats_bound_to_roles_source_and_seeds():
    plan = synthetic_plan()
    assert len(plan.repeats) == 50
    assert [repeat.key for repeat in plan.repeats] == [
        RepeatKey(outer, inner) for outer in OUTER_SEEDS for inner in INNER_IDS
    ]
    assert len({repeat.repeat_id for repeat in plan.repeats}) == 50
    assert all(len(repeat.repeat_id) == 64 for repeat in plan.repeats)
    assert plan.repeat(41003, 51007).seed_map == derive_repeat_seed_map(
        RepeatKey(41003, 51007), RepeatSpec()
    )
    assert plan.spec.confirmatory_dispatch_permitted is False
    assert plan == synthetic_plan()

    other_source = plan_repeats(
        RepeatSpec(), synthetic_binding(release="fabricated-v2"), plan.outer_roles
    )
    assert other_source.plan_digest != plan.plan_digest
    assert {r.repeat_id for r in other_source.repeats}.isdisjoint(
        {r.repeat_id for r in plan.repeats}
    )
    other_roles = synthetic_plan({41002: (2, 3)})
    changed = {
        repeat.key.outer_seed
        for repeat, original in zip(other_roles.repeats, plan.repeats)
        if repeat.repeat_id != original.repeat_id
    }
    assert changed == {41002}


def test_plan_is_immutable_and_invariant_to_role_input_order():
    plan = synthetic_plan()
    with pytest.raises(dataclasses.FrozenInstanceError):
        plan.plan_digest = "0" * 64
    with pytest.raises(dataclasses.FrozenInstanceError):
        plan.repeats[0].seed_map.outer_seed = 1
    assert isinstance(plan.repeats, tuple) and isinstance(plan.outer_roles, tuple)
    shuffled = plan_repeats(RepeatSpec(), synthetic_binding(), tuple(reversed(plan.outer_roles)))
    assert shuffled == plan


def test_plan_rejects_missing_extra_duplicate_and_unsupported_roles():
    roles = tuple(synthetic_roles(outer) for outer in OUTER_SEEDS)
    spec, binding = RepeatSpec(), synthetic_binding()
    assert _code(lambda: plan_repeats(spec, binding, roles[:4])) == "MISSING_OUTER_ROLE"
    assert _code(lambda: plan_repeats(spec, binding, roles + (roles[0],))) == "DUPLICATE_OUTER_ROLE"
    assert _code(
        lambda: plan_repeats(spec, binding, roles[:4] + (synthetic_roles(41006),))
    ) == "UNDECLARED_REPEAT"
    assert _code(lambda: plan_repeats(spec, binding, list(roles))) == "IMMUTABLE_TUPLE"
    small_pool = synthetic_roles(
        41005, target_pool_ids=tuple(f"synthetic:pool:{n}" for n in range(199))
    )
    assert small_pool.support_status == "UNSUPPORTED_ROLE"
    assert _code(lambda: plan_repeats(spec, binding, roles[:4] + (small_pool,))) == "UNSUPPORTED_ROLE"


def test_plan_refuses_any_source_that_is_not_declared_fabricated():
    roles = tuple(synthetic_roles(outer) for outer in OUTER_SEEDS)
    for status in ("development_exposed", "unknown", "custodian_attested"):
        binding = synthetic_binding(exposure_status=status)
        assert _code(lambda: plan_repeats(RepeatSpec(), binding, roles)) == "SYNTHETIC_ONLY"
    assert _code(lambda: synthetic_binding(exposure_status="sealed")) == "EXPOSURE_STATUS"
    assert _code(lambda: synthetic_binding(raw_sha256="not-a-digest")) == "DIGEST"


@pytest.mark.parametrize("change, code", [
    ({"outer_seed": True}, "STRICT_INTEGER"),
    ({"evaluation_order_digest": "0" * 64}, "EVALUATION_ORDER_DIGEST"),
    ({"train_ids": ("synthetic:eval:synthetic-group-a:0",)}, "ROLE_OVERLAP"),
    ({"source_cal_ids": ("synthetic:dup", "synthetic:dup")}, "DUPLICATE_VALUE"),
    ({"evaluation_groups": ("synthetic-group-a",)}, "GROUP_MAP"),
    ({"train_ids": ["synthetic:train:0"]}, "IMMUTABLE_TUPLE"),
    ({"split_profile": ""}, "IDENTIFIER"),
])
def test_role_manifest_rejects_inconsistent_membership(change, code):
    arguments = {"outer_seed": 41001, **change}
    assert _code(lambda: synthetic_roles(**arguments)) == code


def test_legacy_development_seed_allowlist_is_not_relaxed_for_repeat_seeds():
    from shiftguard.experiments import config

    assert config.DEVELOPMENT_SEEDS == (31001, 31002, 31003)
    assert not set(OUTER_SEEDS + INNER_IDS) & set(config.DEVELOPMENT_SEEDS)
    with pytest.raises(ValueError, match="development seed set"):
        config.BaselineConfig(master_seed=OUTER_SEEDS[0])
    assert config.BaselineConfig(master_seed=31001).master_seed == 31001


def test_repeat_package_imports_no_loader_runner_evaluator_or_provider():
    script = (
        "import sys\n"
        "import shiftguard.repeats.models, shiftguard.repeats.seeds\n"
        "import shiftguard.repeats.planning, shiftguard.repeats.validation\n"
        "import shiftguard.repeats.aggregation, shiftguard.repeats.uncertainty\n"
        "import shiftguard.repeats.completion, shiftguard.repeats.synthetic_store\n"
        "prefixes = ('shiftguard.datasets', 'shiftguard.experiments', 'shiftguard.agent',\n"
        "            'shiftguard.api', 'shiftguard.jobs', 'shiftguard.storage',\n"
        "            'shiftguard.predictors', 'shiftguard.calibration', 'shiftguard.protocol',\n"
        "            'shiftguard.preprocessing', 'shiftguard.missingness', 'sklearn')\n"
        "loaded = sorted(name for name in sys.modules if name.startswith(prefixes))\n"
        "print(loaded)\n"
        "raise SystemExit(1 if loaded else 0)\n"
    )
    completed = subprocess.run(
        [sys.executable, "-B", "-c", script], capture_output=True, text=True, timeout=120,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
