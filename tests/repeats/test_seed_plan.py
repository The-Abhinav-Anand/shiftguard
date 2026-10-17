from __future__ import annotations

import dataclasses
import subprocess
import sys

import pytest

from repeat_fixtures import fake_digest, synthetic_binding, synthetic_plan, synthetic_roles
from shiftguard.repeats.models import (
    BANK_DEVELOPMENT_MODE,
    INNER_IDS,
    OUTER_SEEDS,
    RepeatContractError,
    RepeatKey,
    RepeatSpec,
)
from shiftguard.datasets import bank as bank_constants
from shiftguard.repeats import planning
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
    assert seed_plan_digest(RepeatSpec(execution_mode=BANK_DEVELOPMENT_MODE)) == GOLDEN_SEED_PLAN_DIGEST
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


def test_plan_refuses_every_source_except_fabricated_or_the_verified_bank_release():
    roles = tuple(synthetic_roles(outer) for outer in OUTER_SEEDS)
    for status in ("development_exposed", "unknown", "custodian_attested"):
        binding = synthetic_binding(exposure_status=status)
        assert _code(lambda: plan_repeats(RepeatSpec(), binding, roles)) == "SYNTHETIC_ONLY"
    assert _code(lambda: synthetic_binding(exposure_status="sealed")) == "EXPOSURE_STATUS"
    assert _code(lambda: synthetic_binding(raw_sha256="not-a-digest")) == "DIGEST"


def test_verified_bank_constants_equal_the_dataset_owner_and_the_manifest():
    from pathlib import Path
    import json

    assert planning.VERIFIED_BANK_DATASET == bank_constants.FROZEN_BANK_SOURCE["dataset_id"]
    assert planning.VERIFIED_BANK_RELEASE == bank_constants.FROZEN_BANK_SOURCE["source_version"]
    assert planning.VERIFIED_BANK_RAW_SHA256 == bank_constants.FROZEN_BANK_SOURCE["raw_member_sha256"]
    assert planning.VERIFIED_BANK_CLEAN_SHA256 == bank_constants.FROZEN_CLEAN_DIGEST
    manifest_path = Path(__file__).resolve().parents[2] / "var" / "datasets" / "bank.manifest.json"
    if not manifest_path.exists():
        pytest.skip("bank manifest absent")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))  # hash metadata only
    assert planning.VERIFIED_BANK_DATASET == manifest["dataset_id"]
    assert planning.VERIFIED_BANK_RELEASE == manifest["source_version"]
    assert planning.VERIFIED_BANK_RAW_SHA256 == manifest["raw_member_sha256"]
    assert planning.VERIFIED_BANK_CLEAN_SHA256 == manifest["clean_sha256"]


def _dev_binding(**overrides):
    values = {
        "exposure_status": "development_exposed", "dataset": "dev-standin", "release": "dev-v1",
        "raw_sha256": fake_digest("dev-raw"), "clean_sha256": fake_digest("dev-clean"),
    }
    values.update(overrides)
    return synthetic_binding(**values)


def _patch_verified(monkeypatch, binding):
    monkeypatch.setattr(planning, "VERIFIED_BANK_DATASET", binding.dataset)
    monkeypatch.setattr(planning, "VERIFIED_BANK_RELEASE", binding.release)
    monkeypatch.setattr(planning, "VERIFIED_BANK_RAW_SHA256", binding.raw_sha256)
    monkeypatch.setattr(planning, "VERIFIED_BANK_CLEAN_SHA256", binding.clean_sha256)


def test_plan_admits_a_development_binding_only_when_every_verified_value_matches(monkeypatch):
    roles = tuple(synthetic_roles(outer) for outer in OUTER_SEEDS)
    binding = _dev_binding()
    dev_spec = RepeatSpec(execution_mode=BANK_DEVELOPMENT_MODE)
    # Unpinned, the stand-in digests are not the verified release.
    assert not planning.is_verified_bank_development(binding)
    assert _code(lambda: plan_repeats(dev_spec, binding, roles)) == "SYNTHETIC_ONLY"
    _patch_verified(monkeypatch, binding)
    assert planning.is_verified_bank_development(binding)
    assert planning.require_authorized_source(binding) is binding
    plan = plan_repeats(dev_spec, binding, roles)
    assert plan.binding is binding and len(plan.repeats) == 50
    # Each verified field is required on its own.
    for change in ({"dataset": "other"}, {"release": "other"},
                   {"raw_sha256": "e" * 64}, {"clean_sha256": "e" * 64}):
        assert _code(lambda: plan_repeats(dev_spec, _dev_binding(**change), roles)) == "SYNTHETIC_ONLY"
    for status in ("unknown", "custodian_attested"):
        refused = dataclasses.replace(binding, exposure_status=status)
        assert _code(lambda: plan_repeats(dev_spec, refused, roles)) == "SYNTHETIC_ONLY"
    assert _code(lambda: planning.require_authorized_source("binding")) == "REPEAT_SCHEMA"
    # The declared execution mode must match the binding in both directions.
    assert _code(lambda: plan_repeats(RepeatSpec(), binding, roles)) == "EXECUTION_MODE"
    assert _code(lambda: plan_repeats(dev_spec, synthetic_binding(), roles)) == "EXECUTION_MODE"
    assert planning.execution_mode_for(binding) == BANK_DEVELOPMENT_MODE
    assert planning.execution_mode_for(synthetic_binding()) == "synthetic_only"
    assert _code(lambda: RepeatSpec(execution_mode="confirmatory")) == "EXECUTION_MODE"


@pytest.mark.parametrize("field", ("dataset", "release", "raw_sha256", "clean_sha256"))
def test_a_fabricated_binding_may_not_carry_any_verified_bank_identity(field):
    roles = tuple(synthetic_roles(outer) for outer in OUTER_SEEDS)
    real = {
        "dataset": planning.VERIFIED_BANK_DATASET, "release": planning.VERIFIED_BANK_RELEASE,
        "raw_sha256": planning.VERIFIED_BANK_RAW_SHA256,
        "clean_sha256": planning.VERIFIED_BANK_CLEAN_SHA256,
    }
    binding = synthetic_binding(**{field: real[field]})
    assert binding.exposure_status == "synthetic_fabricated"
    assert _code(lambda: plan_repeats(RepeatSpec(), binding, roles)) == "SYNTHETIC_MISLABEL"
    assert _code(lambda: planning.require_authorized_source(binding)) == "SYNTHETIC_MISLABEL"
    assert not planning.is_verified_bank_development(binding)


# Pinned from the synthetic plan before the Bank gate existed; synthetic identities must not move.
SYNTHETIC_PLAN_DIGEST = "5972e7750fb0ca3f19212468a67ba9aa154fe4dacf21e7f1a9f822e377488b13"
SYNTHETIC_SPEC_DIGEST = "78ca295ca89d3739ec73b085039319e5e4ab69aa102127c0aa814cbd1fd351b5"
SYNTHETIC_FIRST_REPEAT_ID = "053a661c27893fbd87d2d542911540e1cb396c955d37b39803ed13b82b6c4af3"
SYNTHETIC_LAST_REPEAT_ID = "27d366c8c44d957940cf6be41c3cebc72e499ea1bc636adfc6639f5c3375362f"


def test_synthetic_plan_identities_are_byte_stable():
    plan = synthetic_plan()
    assert plan.spec.execution_mode == "synthetic_only"
    assert plan.spec.digest == SYNTHETIC_SPEC_DIGEST
    assert plan.plan_digest == SYNTHETIC_PLAN_DIGEST
    assert (plan.repeats[0].repeat_id, plan.repeats[-1].repeat_id) == (
        SYNTHETIC_FIRST_REPEAT_ID, SYNTHETIC_LAST_REPEAT_ID)


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
        # planning pins the verified Bank digests from the dataset owner's constants; importing
        # that module (constants and class definitions, no loader call) is the only exemption.
        "pinned = ('shiftguard.datasets', 'shiftguard.datasets.bank')\n"
        "loaded = sorted(name for name in sys.modules\n"
        "                if name.startswith(prefixes) and name not in pinned)\n"
        "print(loaded)\n"
        "raise SystemExit(1 if loaded else 0)\n"
    )
    completed = subprocess.run(
        [sys.executable, "-B", "-c", script], capture_output=True, text=True, timeout=120,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
