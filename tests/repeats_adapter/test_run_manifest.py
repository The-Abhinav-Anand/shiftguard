"""Gate 8 precondition 3: the frozen run manifest and its freeze script.

Fabricated Bank-shaped rows and throwaway git repositories under tmp paths only. Nothing here
reads var/datasets or any real file, and no coordinate is executed (the freeze tests make the
adapter's execution entry points fail if they were ever called).
"""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from development_fixtures import (
    Lab,
    development_standin_binding,
    development_standin_dataset,
    fake_digest,
    pin_verified_bank,
)
from shiftguard.repeats import run_manifest as rm
from shiftguard.repeats.development_adapter import prepare_outer as REAL_PREPARE_OUTER
from shiftguard.repeats.development_adapter import (
    feature_group_id,
    plan_development_repeats,
    source_row_id,
)
from shiftguard.repeats.models import INNER_IDS, OUTER_SEEDS, RepeatContractError, canonical_digest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
freeze = importlib.import_module("gate8_freeze_run_manifest")

# The real item 9 wording (OWNER_ACTIONS, 17 Oct), including its own quoted "gate8: no" sentence.
ITEM_NINE = (
    "9. **Gate 8 real-Bank repeats: no action needed unless you object (17 Oct):** under your\n"
    "   general delegation, the autopilot decided to run the declared 5x10 Gate 8 repeat schedule\n"
    "   on real Bank. It is development tier only, labelled \"Bank outcomes previously inspected;\n"
    "   not confirmatory\", and the labels stay on this PC. The record is\n"
    "   `..\\research\\gate8-20261009\\AUTHORIZATION-20261017-bank-development-repeats.md`. While\n"
    "   SCI-03 is unresolved, the primary estimate is expected to come out as \"missing evidence\"\n"
    "   by design.\n"
    "   Real data will not be touched before 20 Oct. To stop it, write \"gate8: no\" here.\n"
    "   Status:\n"
)
ITEM_TEN = (
    "\n10. **Commit and push the reviewed Gate 8 adapter change (2 min) - NEW, 17 Oct:** the change\n"
    "    is tested. In a terminal on this PC: run the commit.\n"
)
OWNER_TEXT = ("8. **An earlier item.**\n   Status: done\n\n" + ITEM_NINE + ITEM_TEN).encode("utf-8")
TREE = {
    "shiftguard/__init__.py": b"",
    "shiftguard/repeats/__init__.py": b"",
    "shiftguard/repeats/mod.py": b"VALUE = 1\n",
    "shiftguard/api/other.py": b"OTHER = 1\n",
    "shiftguard/static/bundle.js": b"built frontend\n",
    "scripts/gate8_run_development.py": b"print('a')\n",
    "scripts/gate8_freeze_run_manifest.py": b"print('f')\n",
    "scripts/gate8_resource_preflight.py": b"print('r')\n",
    "scripts/other.py": b"print('b')\n",
    "pyproject.toml": b"[project]\nname = 'x'\n",
    "uv.lock": b"lock-v1\n",
    ".agent/OWNER_ACTIONS.md": OWNER_TEXT,
    "docs/note.md": b"note\n",
}
PROTOCOLS = {
    "SCIENTIFIC_DECISIONS.md": b"decisions v1\n",
    "AUTHORIZATION-20261017-bank-development-repeats.md": b"authorization v1\n",
}


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-c", "safe.directory=*", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
         "-c", "commit.gpgsign=false", "-C", str(repo), *args],
        capture_output=True, check=True)
    return done.stdout.decode()


def make_repo(base: Path) -> Path:
    """A throwaway repository with identical content every time, plus two protocol files."""
    repo = base / "repo"
    repo.mkdir(parents=True)
    git(repo, "init", "-q")
    for name, data in TREE.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    research = base / "research" / "gate8-20261009"
    research.mkdir(parents=True)
    for name, data in PROTOCOLS.items():
        (research / name).write_bytes(data)
    return repo


def protocol_paths(repo: Path) -> tuple[Path, ...]:
    """The one file the binding pins."""
    return (repo.parent / "research" / "gate8-20261009" / "SCIENTIFIC_DECISIONS.md",)


def authorization_path(repo: Path) -> Path:
    return rm.default_authorization_path(repo)


def build_world(base: Path, monkeypatch) -> SimpleNamespace:
    repo = make_repo(base)
    dataset = development_standin_dataset()
    pin_verified_bank(monkeypatch, development_standin_binding(dataset))
    binding = rm.build_development_binding(
        dataset, repo_root=repo, protocol_paths=protocol_paths(repo))
    plan = plan_development_repeats(dataset, binding)
    entries = rm.source_tree_entries(repo)
    manifest = rm.build_run_manifest(
        plan, source_commit=rm.head_commit(repo), source_tree=entries,
        dependency_lock_sha256=hashlib.sha256(TREE["uv.lock"]).hexdigest(),
        dataset_manifest_sha256=fake_digest("dataset-manifest-file"),
        store_root_relative=rm.DEFAULT_STORE_ROOT_RELATIVE,
        authorization_sha256=rm.authorization_sha256(authorization_path(repo)))
    return SimpleNamespace(
        repo=repo, dataset=dataset, binding=binding, plan=plan, manifest=manifest,
        loader=lambda root: (dataset, fake_digest("dataset-manifest-file")))


@pytest.fixture
def world(tmp_path, monkeypatch) -> SimpleNamespace:
    return build_world(tmp_path, monkeypatch)


def code_of(call) -> str:
    with pytest.raises(RepeatContractError) as caught:
        call()
    return caught.value.code


def reseal(manifest: dict) -> dict:
    return rm.seal_manifest(manifest)


# ---------------------------------------------------------------- source tree and cleanliness

def test_source_tree_covers_only_the_declared_scope(world):
    entries = rm.source_tree_entries(world.repo)
    paths = [entry["path"] for entry in entries]
    assert paths == sorted(paths)
    assert paths == [
        "pyproject.toml", "scripts/gate8_freeze_run_manifest.py", "scripts/gate8_run_development.py",
        "shiftguard/__init__.py", "shiftguard/repeats/__init__.py", "shiftguard/repeats/mod.py",
        "uv.lock"]
    for entry in entries:
        assert entry["blob"] == git(world.repo, "rev-parse", f"HEAD:{entry['path']}").strip()


def test_source_tree_hashes_the_bytes_on_disk(world):
    before = rm.source_tree_digest(rm.source_tree_entries(world.repo))
    (world.repo / "shiftguard/repeats/mod.py").write_bytes(b"VALUE = 2\n")
    assert rm.source_tree_digest(rm.source_tree_entries(world.repo)) != before


def test_source_tree_needs_the_repository_top_and_a_lock(world):
    assert code_of(lambda: rm.source_tree_entries(world.repo / "shiftguard")) == "SOURCE_REPO"
    git(world.repo, "rm", "-q", "uv.lock")
    assert code_of(lambda: rm.source_tree_entries(world.repo)) == "SOURCE_FILE_MISSING"


def test_a_tracked_file_deleted_from_disk_is_reported(world):
    (world.repo / "shiftguard/repeats/mod.py").unlink()
    assert code_of(lambda: rm.source_tree_entries(world.repo)) == "SOURCE_FILE_MISSING"
    assert code_of(lambda: rm.require_clean_source(world.repo)) == "SOURCE_DIRTY"


def test_clean_tree_passes_and_out_of_scope_changes_do_not_count(world):
    rm.require_clean_source(world.repo)
    (world.repo / "docs/note.md").write_bytes(b"changed\n")
    (world.repo / "shiftguard/static/bundle.js").write_bytes(b"rebuilt\n")
    (world.repo / "scripts/other.py").write_bytes(b"changed\n")
    (world.repo / "scripts/not_gate8.py").write_bytes(b"new\n")
    (world.repo / "scripts/gate8_new.py").write_bytes(b"new\n")  # a gate8 script outside the closure
    (world.repo / "scripts/gate8_resource_preflight.py").write_bytes(b"changed\n")
    (world.repo / "shiftguard/api/other.py").write_bytes(b"OTHER = 2\n")
    (world.repo / "docs/new.md").write_bytes(b"new\n")
    (world.repo / "var").mkdir()
    (world.repo / "var/x.bin").write_bytes(b"private\n")
    assert rm.dirty_source_paths(world.repo) == []
    rm.require_clean_source(world.repo)


@pytest.mark.parametrize("change", [
    "modify_tracked", "untracked_package_file", "modify_gate8_script", "delete_tracked",
    "modify_package_init",
    "staged_rename", "modify_lock", "modify_pyproject",
])
def test_every_kind_of_source_change_is_dirty(world, change):
    repo = world.repo
    if change == "modify_tracked":
        (repo / "shiftguard/repeats/mod.py").write_bytes(b"VALUE = 9\n")
    elif change == "untracked_package_file":
        (repo / "shiftguard/repeats/new.py").write_bytes(b"x = 1\n")
    elif change == "modify_gate8_script":
        (repo / "scripts/gate8_run_development.py").write_bytes(b"x = 2\n")
    elif change == "modify_package_init":
        (repo / "shiftguard/__init__.py").write_bytes(b"x = 2\n")
    elif change == "delete_tracked":
        (repo / "shiftguard/repeats/mod.py").unlink()
    elif change == "staged_rename":
        git(repo, "mv", "shiftguard/repeats/mod.py", "docs/moved.py")
    elif change == "modify_lock":
        (repo / "uv.lock").write_bytes(b"lock-v2\n")
    else:
        (repo / "pyproject.toml").write_bytes(b"[project]\n")
    assert rm.dirty_source_paths(world.repo)
    assert code_of(lambda: rm.require_clean_source(repo)) == "SOURCE_DIRTY"


# ---------------------------------------------------------------- date gate and owner veto

def test_date_gate_refuses_before_the_twentieth_in_kolkata(world):
    for day in (date(2026, 10, 18), date(2026, 10, 19), date(2025, 12, 31)):
        assert code_of(lambda: rm.require_run_permitted(world.repo, today=day)) == "DATE_GATE"
    for day in (date(2026, 10, 20), date(2026, 10, 21), date(2027, 1, 1)):
        rm.require_run_permitted(world.repo, today=day)


def test_date_gate_uses_the_kolkata_local_date():
    just_before = datetime(2026, 10, 19, 18, 29, tzinfo=timezone.utc)  # 23:59 IST
    just_after = datetime(2026, 10, 19, 18, 30, tzinfo=timezone.utc)  # 00:00 IST
    assert rm.kolkata_today(just_before) == date(2026, 10, 19)
    assert rm.kolkata_today(just_after) == date(2026, 10, 20)
    assert rm.EARLIEST_RUN_DATE == date(2026, 10, 20)


def test_disabling_the_date_gate_still_applies_the_veto(world):
    rm.require_run_permitted(world.repo, today=date(2026, 1, 1), date_gate=False)
    path = world.repo / ".agent/OWNER_ACTIONS.md"
    path.write_text(owner_file("no"), encoding="utf-8")
    assert code_of(lambda: rm.require_run_permitted(
        world.repo, today=date(2026, 1, 1), date_gate=False)) == "OWNER_VETO"


def owner_file(status: str | None = "", *, extra: str = "", item: bool = True) -> str:
    """OWNER_ACTIONS text built from the real item 9 wording with a chosen Status."""
    nine = ITEM_NINE
    if status is None:
        nine = nine.replace("   Status:\n", "")
    elif status:
        nine = nine.replace("   Status:\n", f"   Status: {status}\n")
    return ("8. **An earlier item.**\n   Status: done\n\n" + (nine if item else "") + extra + ITEM_TEN)


@pytest.mark.parametrize("status", [
    "no", "No.", "gate8: no", "GATE8:  NO", "gate 8: no", "Gate-8: no", "gate8 no", "gate8 : no",
    "gate8\uff1a no", "stop", "not yet", "\"gate8: no\"", "wait", "maybe yes",
])
def test_any_non_affirmative_status_text_is_a_veto(world, status):
    text = owner_file(status)
    assert rm.owner_veto_present(text)
    (world.repo / ".agent/OWNER_ACTIONS.md").write_text(text, encoding="utf-8")
    assert code_of(lambda: rm.require_run_permitted(
        world.repo, today=date(2026, 10, 20))) == "OWNER_VETO"


@pytest.mark.parametrize("spelling", [
    "gate8: no", "GATE8:  NO", "gate 8: no", "Gate-8: no", "gate8 no", "gate8 : no",
    "gate_8: no", "gate8\uff1ano", "gate8 - no", "Gate 8 \u2014 no",
])
def test_the_loosened_pattern_vetoes_anywhere_in_the_file(spelling):
    assert rm.owner_veto_present(owner_file("", extra=f"\n9b. **Note.**\n   {spelling}\n")) is True


@pytest.mark.parametrize("status", ["yes", "OK", "Go", "proceed", "Allowed.", "gate8: yes", "okay"])
def test_explicit_affirmative_statuses_proceed(world, status):
    (world.repo / ".agent/OWNER_ACTIONS.md").write_text(owner_file(status), encoding="utf-8")
    rm.require_run_permitted(world.repo, today=date(2026, 10, 20))


def test_the_real_wording_with_an_empty_status_proceeds_and_its_instruction_sentence_is_ignored(world):
    assert rm.owner_veto_present(OWNER_TEXT.decode()) is False
    assert rm.owner_veto_state(owner_file("")) is None
    rm.require_run_permitted(world.repo, today=date(2026, 10, 20))


def test_a_missing_item_or_status_line_or_file_fails_closed(world):
    assert rm.owner_veto_state(owner_file("", item=False)) == "item 9 not found"
    assert rm.owner_veto_state(owner_file(None)) == "item 9 has no Status line"
    # A Status line that belongs to a different item does not count for item 9.
    assert rm.owner_veto_present(owner_file(None, extra="")) is True
    for text in (owner_file("", item=False), owner_file(None)):
        (world.repo / ".agent/OWNER_ACTIONS.md").write_text(text, encoding="utf-8")
        assert code_of(lambda: rm.require_run_permitted(
            world.repo, today=date(2026, 10, 20))) == "OWNER_VETO"
    (world.repo / ".agent/OWNER_ACTIONS.md").unlink()
    assert code_of(lambda: rm.require_run_permitted(
        world.repo, today=date(2026, 10, 20))) == "OWNER_VETO"


# ---------------------------------------------------------------- the development binding

def test_binding_digests_cover_what_the_docstring_says(world):
    binding, dataset, repo = world.binding, world.dataset, world.repo
    assert binding.exposure_status == "development_exposed"
    assert (binding.dataset, binding.release) == (
        development_standin_binding(dataset).dataset, development_standin_binding(dataset).release)
    assert binding.raw_sha256 == dataset.raw_hash and binding.clean_sha256 == dataset.clean_hash
    schema = canonical_digest(["gate8-feature-schema-v1", list(rm.BANK_FEATURES), rm.FEATURE_GROUP_VERSION])
    assert binding.feature_schema_sha256 == schema == rm.feature_schema_digest()
    pairs = [
        [source_row_id(binding, row["row_id"]), feature_group_id(row, schema)]
        for row in sorted(dataset.rows, key=lambda r: r["row_id"])]
    assert binding.group_manifest_sha256 == canonical_digest(
        ["gate8-group-manifest-v1", rm.FEATURE_GROUP_VERSION, schema, pairs])
    assert binding.source_sha256 == rm.source_tree_digest(rm.source_tree_entries(repo))
    assert binding.dependency_lock_sha256 == hashlib.sha256(TREE["uv.lock"]).hexdigest()
    assert binding.protocol_review_sha256 == rm.protocol_review_digest(protocol_paths(repo))


def test_binding_follows_the_source_lock_and_protocol_bytes(world):
    paths = protocol_paths(world.repo)

    def build():
        return rm.build_development_binding(
            world.dataset, repo_root=world.repo, protocol_paths=paths)

    assert build() == world.binding
    paths[0].write_bytes(b"decisions v2\n")
    changed_protocol = build()
    assert changed_protocol.protocol_review_sha256 != world.binding.protocol_review_sha256
    assert changed_protocol.source_sha256 == world.binding.source_sha256
    (world.repo / "uv.lock").write_bytes(b"lock-v2\n")
    changed_lock = build()
    assert changed_lock.dependency_lock_sha256 != world.binding.dependency_lock_sha256
    assert changed_lock.source_sha256 != world.binding.source_sha256
    # The protocol digest does not depend on the order the paths are given in.
    both = (paths[0], authorization_path(world.repo))
    assert rm.protocol_review_digest(both) == rm.protocol_review_digest(tuple(reversed(both)))


def test_binding_refuses_everything_that_is_not_the_verified_release(world, monkeypatch):
    kwargs = dict(repo_root=world.repo, protocol_paths=protocol_paths(world.repo))
    other = development_standin_dataset()
    other = type(other)(other.rows, raw_hash=fake_digest("another-raw"), clean_hash=other.clean_hash)
    assert code_of(lambda: rm.build_development_binding(other, **kwargs)) == "SOURCE_BINDING_MISMATCH"
    assert code_of(lambda: rm.build_development_binding("rows", **kwargs)) == "DATASET_SCHEMA"
    tampered = [dict(row) for row in world.dataset.rows]
    tampered[0]["job"] = "retired" if tampered[0]["job"] != "retired" else "admin."
    broken = type(world.dataset)(
        tampered, raw_hash=world.dataset.raw_hash, clean_hash=world.dataset.clean_hash)
    assert code_of(lambda: rm.build_development_binding(broken, **kwargs)) == "SOURCE_BINDING_MISMATCH"
    paths = protocol_paths(world.repo)
    assert code_of(lambda: rm.build_development_binding(
        world.dataset, repo_root=world.repo, protocol_paths=())) == "PROTOCOL_FILES"
    assert code_of(lambda: rm.build_development_binding(
        world.dataset, repo_root=world.repo, protocol_paths=(paths[0], paths[0]))) == "PROTOCOL_FILES"
    assert code_of(lambda: rm.build_development_binding(
        world.dataset, repo_root=world.repo,
        protocol_paths=(paths[0], paths[0].with_name("missing.md")))) == "PROTOCOL_FILES"
    monkeypatch.undo()  # the real verified identity is back: fabricated rows are not that release
    assert code_of(lambda: rm.build_development_binding(
        world.dataset, repo_root=world.repo, protocol_paths=paths)) == "SOURCE_BINDING_MISMATCH"


# ---------------------------------------------------------------- the manifest

def test_manifest_has_exactly_the_declared_keys_and_a_valid_digest(world):
    manifest = world.manifest
    assert tuple(sorted(manifest)) == rm.MANIFEST_KEYS
    body = {key: value for key, value in manifest.items() if key != "manifest_digest"}
    assert manifest["manifest_digest"] == canonical_digest(body)
    rm.verify_run_manifest(manifest, world.plan, repo_root=world.repo)


def test_manifest_content_matches_the_plan(world):
    manifest, plan = world.manifest, world.plan
    assert manifest["schema"] == "gate8-run-manifest-v1"
    assert manifest["label"] == "development; Bank outcomes previously inspected; not confirmatory"
    assert (manifest["execution_tier"], manifest["split_profile"]) == (
        "development", "bank_overlap_diagnostic")
    assert manifest["claim_scope"] == "development_bank_outcomes_previously_inspected_not_confirmatory"
    assert manifest["source_commit"] == git(world.repo, "rev-parse", "HEAD").strip()
    assert manifest["plan_digest"] == plan.plan_digest
    assert manifest["binding_digest"] == plan.binding.digest and manifest["binding"] == plan.binding.to_canonical()
    assert manifest["spec_digest"] == plan.spec.digest and manifest["spec"] == plan.spec.to_canonical()
    assert [(s["outer_seed"], s["inner_id"], s["repeat_id"], s["seed_map_digest"])
            for s in manifest["schedule"]] == [
        (r.key.outer_seed, r.key.inner_id, r.repeat_id, r.seed_map.digest) for r in plan.repeats]
    assert [(s["outer_seed"], s["inner_id"]) for s in manifest["schedule"]] == [
        (o, i) for o in OUTER_SEEDS for i in INNER_IDS]
    assert len(manifest["roles"]) == len(OUTER_SEEDS)
    for role, source in zip(manifest["roles"], plan.outer_roles):
        assert role["outer_seed"] == source.outer_seed
        assert role["role_manifest_digest"] == source.digest
        assert role["evaluation_order_digest"] == source.evaluation_order_digest
        assert role["counts"]["evaluation"] == len(source.evaluation_ids)
        assert role["counts"]["train"] == len(source.train_ids)
        assert role["counts"]["target_pool"] == len(source.target_pool_ids)
    assert manifest["primary_contrast"]["contrast"] == (
        "target_temperature minus source_fraction_binned_temperature")
    assert manifest["primary_contrast"]["budget"] == 50
    assert manifest["primary_contrast"]["cell_count"] == 8
    assert manifest["primary_contrast"]["metric"] == "binary_brier"
    assert manifest["analysis"]["interval"] == "conditional_group_bootstrap"
    assert manifest["analysis"]["sensitivity_summaries"] == ["split_profile", "seed"]
    assert manifest["store_record_versions"]["coordinate_record"] == "gate8-dev-coordinate-v1"
    assert manifest["store_root_relative"] == "var/gate8-private/bank-development-v1"
    assert manifest["source_tree_digest"] == rm.source_tree_digest(manifest["source_tree"])
    assert manifest["dependency_lock_sha256"] == hashlib.sha256(TREE["uv.lock"]).hexdigest()


def test_dump_is_canonical_and_byte_identical(world, tmp_path):
    kwargs = dict(
        source_commit=world.manifest["source_commit"], source_tree=rm.source_tree_entries(world.repo),
        dependency_lock_sha256=world.manifest["dependency_lock_sha256"],
        dataset_manifest_sha256=world.manifest["dataset_manifest_sha256"],
        store_root_relative=rm.DEFAULT_STORE_ROOT_RELATIVE,
        authorization_sha256=world.manifest["authorization_sha256_at_freeze"])
    again = rm.build_run_manifest(world.plan, **kwargs)
    assert again == world.manifest
    first, second = rm.dump_manifest(world.manifest), rm.dump_manifest(again)
    assert first == second
    assert first.endswith(b"\n") and not first.endswith(b"\n\n")
    first.decode("ascii")
    assert json.dumps(json.loads(first), sort_keys=True, separators=(",", ":")).encode() + b"\n" == first
    path = tmp_path / "manifest.json"
    path.write_bytes(first)
    assert rm.load_manifest(path) == world.manifest


def test_load_manifest_refuses_non_canonical_or_unreadable_files(world, tmp_path):
    path = tmp_path / "m.json"
    path.write_text(json.dumps(world.manifest, indent=2), encoding="ascii")
    assert code_of(lambda: rm.load_manifest(path)) == "MANIFEST_NOT_CANONICAL"
    path.write_bytes(b"{not json")
    assert code_of(lambda: rm.load_manifest(path)) == "MANIFEST_UNREADABLE"
    assert code_of(lambda: rm.load_manifest(tmp_path / "absent.json")) == "MANIFEST_UNREADABLE"
    path.write_bytes(b"[1]\n")
    assert code_of(lambda: rm.load_manifest(path)) == "MANIFEST_KEYS"


def _all_keys(value, found=None):
    found = set() if found is None else found
    if isinstance(value, dict):
        for key, item in value.items():
            found.add(key)
            _all_keys(item, found)
    elif isinstance(value, list):
        for item in value:
            _all_keys(item, found)
    return found


def test_manifest_holds_no_row_ids_groups_labels_or_losses(world):
    text = rm.dump_manifest(world.manifest).decode("ascii")
    for role in world.plan.outer_roles:
        for row_id in (role.evaluation_ids[0], role.train_ids[0], role.target_pool_ids[0]):
            assert row_id not in text
        for group in role.evaluation_groups[:5]:
            assert group not in text
    keys = _all_keys(world.manifest)
    assert not keys & {
        "y", "labels", "loss", "losses", "paired_loss_sum_by_group", "sums", "evaluation_ids",
        "train_ids", "target_pool_ids", "source_cal_ids", "evaluation_groups", "group_map", "row_id"}
    assert "dev-standin-bank:" not in text
    assert not any("loss" in key or "brier_score" in key for key in keys)


TAMPERS = {
    "analysis": (lambda m: {**m["analysis"], "interval": "x"}, "MANIFEST_DECLARATION"),
    "binding": (lambda m: {**m["binding"], "dataset": "other"}, "MANIFEST_BINDING"),
    "binding_digest": (lambda m: "0" * 64, "MANIFEST_BINDING"),
    "claim_scope": (lambda m: "confirmatory", "MANIFEST_PLAN"),
    "dependency_lock_sha256": (lambda m: "1" * 64, "MANIFEST_BINDING"),
    "environment": (lambda m: {**m["environment"], "python": "2.7.0"}, "MANIFEST_ENVIRONMENT"),
    "execution_tier": (lambda m: "confirmatory", "MANIFEST_PLAN"),
    "label": (lambda m: "confirmatory", "MANIFEST_SCHEMA"),
    "plan_digest": (lambda m: "2" * 64, "MANIFEST_PLAN"),
    "primary_contrast": (lambda m: {**m["primary_contrast"], "budget": 25}, "MANIFEST_DECLARATION"),
    "roles": (lambda m: [{**m["roles"][0], "role_manifest_digest": "3" * 64}, *m["roles"][1:]],
              "MANIFEST_ROLES"),
    "schedule": (lambda m: [m["schedule"][1], m["schedule"][0], *m["schedule"][2:]], "MANIFEST_SCHEDULE"),
    "schema": (lambda m: "gate8-run-manifest-v2", "MANIFEST_SCHEMA"),
    "seed_plan_digest": (lambda m: "4" * 64, "MANIFEST_PLAN"),
    "source_commit": (lambda m: "5" * 40, "MANIFEST_SOURCE_COMMIT"),
    "source_tree": (lambda m: [m["source_tree"][0], {**m["source_tree"][1], "blob": "6" * 40},
                               *m["source_tree"][2:]], "MANIFEST_BINDING"),
    "source_tree_digest": (lambda m: "7" * 64, "MANIFEST_SOURCE_TREE"),
    "spec": (lambda m: {**m["spec"], "outer_seeds": [41001]}, "MANIFEST_SPEC"),
    "spec_digest": (lambda m: "8" * 64, "MANIFEST_SPEC"),
    "split_profile": (lambda m: "row_stratified", "MANIFEST_PLAN"),
    "store_record_versions": (lambda m: {**m["store_record_versions"], "store_schema": "x"},
                              "MANIFEST_DECLARATION"),
    "store_root_relative": (lambda m: "var/elsewhere/store", "MANIFEST_STORE_ROOT"),
}


def test_the_tamper_table_covers_every_key_except_the_two_special_cases():
    assert set(TAMPERS) | {
        "manifest_digest", "dataset_manifest_sha256", "authorization_sha256_at_freeze"
    } == set(rm.MANIFEST_KEYS)


@pytest.mark.parametrize("key", sorted(TAMPERS))
def test_every_tamper_is_rejected_with_its_code(world, key):
    mutate, code = TAMPERS[key]
    tampered = copy.deepcopy(world.manifest)
    tampered[key] = mutate(world.manifest)
    assert tampered[key] != world.manifest[key]
    # Without resealing, the digest self-check catches it first.
    assert code_of(lambda: rm.verify_run_manifest(tampered, world.plan, repo_root=world.repo)) == (
        "MANIFEST_DIGEST")
    # A tamperer who recomputes the digest meets the specific check.
    assert code_of(lambda: rm.verify_run_manifest(
        reseal(tampered), world.plan, repo_root=world.repo)) == code


def test_a_forged_manifest_digest_and_the_dataset_file_hash_are_checked(world):
    tampered = {**world.manifest, "manifest_digest": "9" * 64}
    assert code_of(lambda: rm.verify_run_manifest(tampered, world.plan, repo_root=world.repo)) == (
        "MANIFEST_DIGEST")
    rm.verify_run_manifest(
        world.manifest, world.plan, repo_root=world.repo,
        dataset_manifest_sha256=world.manifest["dataset_manifest_sha256"])
    assert code_of(lambda: rm.verify_run_manifest(
        world.manifest, world.plan, repo_root=world.repo,
        dataset_manifest_sha256=fake_digest("a different file"))) == "MANIFEST_DATASET"
    changed = reseal({**world.manifest, "dataset_manifest_sha256": fake_digest("other")})
    assert code_of(lambda: rm.verify_run_manifest(
        changed, world.plan, repo_root=world.repo,
        dataset_manifest_sha256=world.manifest["dataset_manifest_sha256"])) == "MANIFEST_DATASET"


def test_extra_missing_and_non_dict_manifests_are_rejected(world):
    extra = reseal({**world.manifest, "extra": 1})
    assert code_of(lambda: rm.verify_run_manifest(extra, world.plan, repo_root=world.repo)) == "MANIFEST_KEYS"
    for key in rm.MANIFEST_KEYS:
        missing = {k: v for k, v in world.manifest.items() if k != key}
        assert code_of(lambda: rm.verify_run_manifest(
            missing, world.plan, repo_root=world.repo)) == "MANIFEST_KEYS"
    assert code_of(lambda: rm.verify_run_manifest([], world.plan, repo_root=world.repo)) == "MANIFEST_KEYS"


@pytest.mark.parametrize("mutation", [
    "reverse", "swap_within_outer", "drop_last", "duplicate", "repeat_id", "seed_map_digest", "inner_id",
])
def test_schedule_tampers_are_rejected(world, mutation):
    schedule = copy.deepcopy(world.manifest["schedule"])
    if mutation == "reverse":
        schedule.reverse()
    elif mutation == "swap_within_outer":
        schedule[3], schedule[4] = schedule[4], schedule[3]
    elif mutation == "drop_last":
        schedule.pop()
    elif mutation == "duplicate":
        schedule[1] = copy.deepcopy(schedule[0])
    elif mutation == "repeat_id":
        schedule[7]["repeat_id"] = "a" * 64
    elif mutation == "seed_map_digest":
        schedule[7]["seed_map_digest"] = "b" * 64
    else:
        schedule[7]["inner_id"] = 51001
    tampered = reseal({**world.manifest, "schedule": schedule})
    assert code_of(lambda: rm.verify_run_manifest(tampered, world.plan, repo_root=world.repo)) == (
        "MANIFEST_SCHEDULE")


@pytest.mark.parametrize("mutation", ["reverse", "digest", "count", "order_digest", "extra_key"])
def test_role_tampers_are_rejected(world, mutation):
    roles = copy.deepcopy(world.manifest["roles"])
    if mutation == "reverse":
        roles.reverse()
    elif mutation == "digest":
        roles[2]["role_manifest_digest"] = "c" * 64
    elif mutation == "count":
        roles[2]["counts"]["evaluation"] += 1
    elif mutation == "order_digest":
        roles[2]["evaluation_order_digest"] = "d" * 64
    else:
        roles[2]["evaluation_ids"] = ["x"]
    tampered = reseal({**world.manifest, "roles": roles})
    assert code_of(lambda: rm.verify_run_manifest(tampered, world.plan, repo_root=world.repo)) == (
        "MANIFEST_ROLES")


def test_a_different_plan_is_rejected(world, monkeypatch):
    # Same dataset, but the protocol files differ, so the binding and every repeat id differ.
    protocol_paths(world.repo)[0].write_bytes(b"decisions v2\n")
    binding = rm.build_development_binding(
        world.dataset, repo_root=world.repo, protocol_paths=protocol_paths(world.repo))
    other_plan = plan_development_repeats(world.dataset, binding)
    assert other_plan.plan_digest != world.plan.plan_digest
    assert code_of(lambda: rm.verify_run_manifest(
        world.manifest, other_plan, repo_root=world.repo)) == "MANIFEST_BINDING"


def test_source_drift_is_rejected_for_every_kind_of_change(world):
    repo = world.repo
    rm.verify_run_manifest(world.manifest, world.plan, repo_root=repo)
    (repo / "shiftguard/repeats/mod.py").write_bytes(b"VALUE = 3\n")
    assert code_of(lambda: rm.verify_run_manifest(world.manifest, world.plan, repo_root=repo)) == (
        "MANIFEST_SOURCE_DRIFT")
    (repo / "shiftguard/repeats/mod.py").write_bytes(TREE["shiftguard/repeats/mod.py"])
    rm.verify_run_manifest(world.manifest, world.plan, repo_root=repo)
    (repo / "shiftguard/repeats/extra.py").write_bytes(b"x = 1\n")
    git(repo, "add", "-A")
    assert code_of(lambda: rm.verify_run_manifest(world.manifest, world.plan, repo_root=repo)) == (
        "MANIFEST_SOURCE_DRIFT")
    git(repo, "rm", "-q", "-f", "shiftguard/repeats/extra.py")
    git(repo, "rm", "-q", "shiftguard/repeats/mod.py")
    assert code_of(lambda: rm.verify_run_manifest(world.manifest, world.plan, repo_root=repo)) == (
        "MANIFEST_SOURCE_DRIFT")


def test_a_later_commit_of_non_source_files_keeps_the_manifest_valid(world):
    repo = world.repo
    (repo / "docs/note.md").write_bytes(b"manifest committed here\n")
    git(repo, "commit", "-q", "-am", "docs only")
    assert rm.head_commit(repo) != world.manifest["source_commit"]
    rm.verify_run_manifest(world.manifest, world.plan, repo_root=repo)
    # A committed source change is still drift, even though the tree is clean again.
    (repo / "shiftguard/repeats/mod.py").write_bytes(b"VALUE = 4\n")
    git(repo, "commit", "-q", "-am", "source change")
    rm.require_clean_source(repo)
    assert code_of(lambda: rm.verify_run_manifest(world.manifest, world.plan, repo_root=repo)) == (
        "MANIFEST_SOURCE_DRIFT")


def test_a_source_commit_that_is_not_in_history_is_rejected(world):
    git(world.repo, "checkout", "-q", "--orphan", "other")
    git(world.repo, "commit", "-q", "--allow-empty", "-m", "unrelated")
    assert code_of(lambda: rm.verify_run_manifest(
        world.manifest, world.plan, repo_root=world.repo)) == "MANIFEST_SOURCE_COMMIT"


@pytest.mark.parametrize("field, value, code", [
    ("source_commit", "A" * 40, "MANIFEST_SOURCE_FIELDS"),
    ("source_commit", "a" * 39, "MANIFEST_SOURCE_FIELDS"),
    ("dependency_lock_sha256", "xyz", "MANIFEST_SOURCE_FIELDS"),
    ("dataset_manifest_sha256", "A" * 64, "MANIFEST_SOURCE_FIELDS"),
    ("store_root_relative", "var/gate8-private/", "MANIFEST_STORE_ROOT"),
    ("store_root_relative", "var/gate8-private/../x", "MANIFEST_STORE_ROOT"),
    ("store_root_relative", "/var/gate8-private/x", "MANIFEST_STORE_ROOT"),
    ("store_root_relative", "var\\gate8-private\\x", "MANIFEST_STORE_ROOT"),
    ("store_root_relative", "var/other/x", "MANIFEST_STORE_ROOT"),
    ("store_root_relative", "var/gate8-private//x", "MANIFEST_STORE_ROOT"),
    ("source_tree", [], "MANIFEST_SOURCE_FIELDS"),
])
def test_build_refuses_malformed_inputs(world, field, value, code):
    kwargs = dict(
        source_commit=world.manifest["source_commit"], source_tree=rm.source_tree_entries(world.repo),
        dependency_lock_sha256=world.manifest["dependency_lock_sha256"],
        dataset_manifest_sha256=world.manifest["dataset_manifest_sha256"],
        store_root_relative=rm.DEFAULT_STORE_ROOT_RELATIVE,
        authorization_sha256=world.manifest["authorization_sha256_at_freeze"])
    kwargs[field] = value
    assert code_of(lambda: rm.build_run_manifest(world.plan, **kwargs)) == code


def test_build_refuses_unsorted_or_malformed_trees(world):
    tree = rm.source_tree_entries(world.repo)
    base = dict(
        source_commit=world.manifest["source_commit"],
        dependency_lock_sha256=world.manifest["dependency_lock_sha256"],
        dataset_manifest_sha256=world.manifest["dataset_manifest_sha256"],
        store_root_relative=rm.DEFAULT_STORE_ROOT_RELATIVE,
        authorization_sha256=world.manifest["authorization_sha256_at_freeze"])
    for bad in (list(reversed(tree)), tree + [tree[0]], [{"path": "a"}] + tree,
                [{**tree[0], "path": "../x"}] + tree[1:], [{**tree[0], "path": "C:\\x"}] + tree[1:]):
        assert code_of(lambda: rm.build_run_manifest(
            world.plan, source_tree=bad, **base)) == "MANIFEST_SOURCE_FIELDS"
    dropped = [entry for entry in tree if entry["path"] != "uv.lock"]
    assert code_of(lambda: rm.build_run_manifest(
        world.plan, source_tree=dropped, **base)) == "MANIFEST_DEPENDENCY_LOCK"


def test_a_binding_that_does_not_describe_the_tree_is_refused(world):
    entries = rm.source_tree_entries(world.repo)
    entries[1] = {**entries[1], "blob": "e" * 40}
    assert code_of(lambda: rm.build_run_manifest(
        world.plan, source_commit=world.manifest["source_commit"], source_tree=entries,
        dependency_lock_sha256=world.manifest["dependency_lock_sha256"],
        dataset_manifest_sha256=world.manifest["dataset_manifest_sha256"],
        store_root_relative=rm.DEFAULT_STORE_ROOT_RELATIVE,
        authorization_sha256=world.manifest["authorization_sha256_at_freeze"])) == "MANIFEST_BINDING"


def test_the_manifest_is_generic_over_a_synthetic_plan():
    lab = Lab()
    entries = [{"path": "uv.lock", "blob": "b" * 40}]
    lock = fake_digest("lock")[:64]
    first = rm.build_run_manifest(
        lab.plan, source_commit="a" * 40, source_tree=entries, dependency_lock_sha256=lock,
        dataset_manifest_sha256=fake_digest("m"), store_root_relative="var/gate8-private/x", authorization_sha256="c" * 64)
    second = rm.build_run_manifest(
        lab.plan, source_commit="a" * 40, source_tree=entries, dependency_lock_sha256=lock,
        dataset_manifest_sha256=fake_digest("m"), store_root_relative="var/gate8-private/x", authorization_sha256="c" * 64)
    assert rm.dump_manifest(first) == rm.dump_manifest(second)
    assert first["claim_scope"] == "synthetic_engineering_fixture_not_a_research_finding"
    assert len(first["schedule"]) == 50 and first["plan_digest"] == lab.plan.plan_digest


# ---------------------------------------------------------------- the freeze script

GUARDED = (
    "prepare_outer", "execute_coordinate", "fit_temperature", "fit_train_preprocessor",
    "fit_tree_preprocessor", "fit_initial_logistic_regression", "fit_initial_random_forest",
    "FinalTestEvaluator", "LabelBlindTargetProvider", "fit_source_fraction_binned_temperature",
)


@pytest.fixture
def no_execution(monkeypatch):
    """Every fitting, scoring and execution entry point the adapter owns records and refuses.

    Freezing reaches the adapter (planning builds roles through it) but must never reach any of
    these; ``test_the_execution_guard_is_not_vacuous`` proves the guard fires on real execution.
    """
    from shiftguard.repeats import development_adapter as adapter

    calls: list[str] = []

    def guard(name):
        def forbidden(*args, **kwargs):
            calls.append(name)
            raise AssertionError(f"freezing must not reach {name}")
        return forbidden

    for name in GUARDED:
        monkeypatch.setattr(adapter, name, guard(name))
    yield calls
    assert calls == []


def test_the_execution_guard_is_not_vacuous(world, no_execution):
    # The real, unpatched prepare_outer runs against the patched fitting/scoring names it uses.
    with pytest.raises(AssertionError):
        REAL_PREPARE_OUTER(world.dataset, world.plan, OUTER_SEEDS[0])
    assert no_execution and no_execution[0] in GUARDED
    no_execution.clear()  # the control call above is the only expected one


def test_freeze_writes_a_verifiable_manifest_and_prints_only_digests(world, no_execution, capsys):
    assert freeze.main([], dataset_loader=world.loader, today=date(2026, 10, 20), repo_root=world.repo) == 0
    assert no_execution == []
    printed = capsys.readouterr().out
    written = world.repo / rm.DEFAULT_MANIFEST_RELATIVE
    manifest = rm.load_manifest(written)
    assert manifest == world.manifest
    rm.verify_run_manifest(manifest, world.plan, repo_root=world.repo)
    assert f"manifest_digest {manifest['manifest_digest']}" in printed
    assert f"plan_digest {world.plan.plan_digest}" in printed
    assert "coordinates 50 outer_seeds 5" in printed
    assert "files in the source scope must not change until the campaign finishes" in printed
    assert "dev-standin-bank:" not in printed and "row" not in printed.replace("outer_seeds", "")
    # The manifest file is outside the source scope: the tree stays clean, and verification holds.
    rm.require_clean_source(world.repo)


def test_freeze_is_deterministic_and_never_overwrites(world, no_execution, capsys, tmp_path):
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    for out in (first, second):
        assert freeze.main(
            ["--out", str(out)], dataset_loader=world.loader, today=date(2026, 10, 20),
            repo_root=world.repo) == 0
    assert first.read_bytes() == second.read_bytes()
    capsys.readouterr()
    before = first.read_bytes()
    assert freeze.main(
        ["--out", str(first)], dataset_loader=world.loader, today=date(2026, 10, 20),
        repo_root=world.repo) == 2
    assert "OUT_EXISTS" in capsys.readouterr().out
    assert first.read_bytes() == before


def test_freeze_refuses_before_the_date_and_when_vetoed_or_dirty(world, no_execution, capsys, tmp_path):
    out = tmp_path / "m.json"
    argv = ["--out", str(out)]
    run = lambda day: freeze.main(argv, dataset_loader=world.loader, today=day, repo_root=world.repo)  # noqa: E731
    assert run(date(2026, 10, 19)) == 2 and "DATE_GATE" in capsys.readouterr().out
    assert not out.exists()
    (world.repo / ".agent/OWNER_ACTIONS.md").write_text(owner_file("no"), encoding="utf-8")
    assert run(date(2026, 10, 21)) == 2 and "OWNER_VETO" in capsys.readouterr().out
    (world.repo / ".agent/OWNER_ACTIONS.md").write_bytes(OWNER_TEXT)
    (world.repo / "shiftguard/repeats/mod.py").write_bytes(b"VALUE = 5\n")
    assert run(date(2026, 10, 21)) == 2 and "SOURCE_DIRTY" in capsys.readouterr().out
    assert not out.exists()


def test_freeze_without_the_date_gate_needs_an_injected_loader(world, no_execution, capsys, tmp_path):
    assert freeze.main(["--no-date-gate"], today=date(2026, 1, 1), repo_root=world.repo) == 2
    assert "DATE_GATE_REQUIRED" in capsys.readouterr().out
    out = tmp_path / "early.json"
    assert freeze.main(
        ["--no-date-gate", "--out", str(out)], dataset_loader=world.loader, today=date(2026, 1, 1),
        repo_root=world.repo) == 0
    assert out.exists()


def test_freeze_refuses_an_output_inside_the_source_tree(world, no_execution, capsys):
    out = world.repo / "shiftguard/repeats/manifest.json"
    assert freeze.main(
        ["--out", str(out)], dataset_loader=world.loader, today=date(2026, 10, 20),
        repo_root=world.repo) == 2
    assert "OUT_IN_SOURCE" in capsys.readouterr().out and not out.exists()


def test_freeze_refuses_a_dataset_that_is_not_the_verified_release(world, no_execution, capsys, tmp_path):
    other = development_standin_dataset()
    other = type(other)(other.rows, raw_hash=fake_digest("not-the-release"), clean_hash=other.clean_hash)
    out = tmp_path / "bad.json"
    assert freeze.main(
        ["--out", str(out)], dataset_loader=lambda root: (other, fake_digest("m")),
        today=date(2026, 10, 20), repo_root=world.repo) == 2
    assert "SOURCE_BINDING_MISMATCH" in capsys.readouterr().out and not out.exists()


def test_freeze_overrides_need_an_injected_loader(world, no_execution, capsys, tmp_path):
    for argv in (
        ["--out", str(tmp_path / "x.json")], ["--store-root-relative", "var/gate8-private/other"],
        ["--protocol", str(protocol_paths(world.repo)[0])],
        ["--authorization", str(authorization_path(world.repo))],
    ):
        assert freeze.main(argv) == 2
        assert "OVERRIDE_REQUIRES_LOADER" in capsys.readouterr().out
    assert freeze.main([], today=date(2026, 10, 20)) == 2
    assert "OVERRIDE_REQUIRES_LOADER" in capsys.readouterr().out
    assert not (tmp_path / "x.json").exists()


# ---------------------------------------------------------------- git-normalized blobs and the commit tree

def test_a_crlf_checkout_hashes_like_the_commit_and_still_verifies(world):
    repo = world.repo
    git(repo, "config", "core.autocrlf", "true")
    for path in ("shiftguard/repeats/mod.py", "uv.lock"):
        data = (repo / path).read_bytes()
        (repo / path).write_bytes(data.replace(b"\n", b"\r\n"))
    assert rm.source_tree_entries(repo) == world.manifest["source_tree"]
    assert rm.dependency_lock_sha256(repo) == world.manifest["dependency_lock_sha256"]
    rm.verify_run_manifest(world.manifest, world.plan, repo_root=repo)
    # Without a normalizing rule the raw CRLF bytes are a real change.
    git(repo, "config", "core.autocrlf", "false")
    assert rm.source_tree_entries(repo) != world.manifest["source_tree"]


def test_an_ancestor_commit_whose_source_differs_is_rejected(world):
    repo = world.repo
    first_commit = rm.head_commit(repo)
    (repo / "shiftguard/repeats/mod.py").write_bytes(b"VALUE = 99\n")
    git(repo, "commit", "-q", "-am", "source change")
    entries = rm.source_tree_entries(repo)
    binding = rm.build_development_binding(
        world.dataset, repo_root=repo, protocol_paths=protocol_paths(repo))
    plan = plan_development_repeats(world.dataset, binding)
    kwargs = dict(
        source_tree=entries, dependency_lock_sha256=rm.dependency_lock_sha256(repo),
        dataset_manifest_sha256=world.manifest["dataset_manifest_sha256"],
        store_root_relative=rm.DEFAULT_STORE_ROOT_RELATIVE,
        authorization_sha256=world.manifest["authorization_sha256_at_freeze"])
    honest = rm.build_run_manifest(plan, source_commit=rm.head_commit(repo), **kwargs)
    rm.verify_run_manifest(honest, plan, repo_root=repo)
    # The frozen tree is the current one, but it names an ancestor that held different source.
    forged = rm.build_run_manifest(plan, source_commit=first_commit, **kwargs)
    assert code_of(lambda: rm.verify_run_manifest(forged, plan, repo_root=repo)) == "MANIFEST_SOURCE_COMMIT"


def test_a_tree_that_is_not_in_the_named_commit_is_rejected(world):
    repo = world.repo
    (repo / "shiftguard/repeats/untracked_extra.py").write_bytes(b"x = 1\n")
    git(repo, "add", "-A")  # staged, never committed: the index has it, HEAD does not
    entries = rm.source_tree_entries(repo)
    assert any(e["path"].endswith("untracked_extra.py") for e in entries)
    binding = rm.build_development_binding(
        world.dataset, repo_root=repo, protocol_paths=protocol_paths(repo))
    plan = plan_development_repeats(world.dataset, binding)
    manifest = rm.build_run_manifest(
        plan, source_commit=rm.head_commit(repo), source_tree=entries,
        dependency_lock_sha256=rm.dependency_lock_sha256(repo),
        dataset_manifest_sha256=world.manifest["dataset_manifest_sha256"],
        store_root_relative=rm.DEFAULT_STORE_ROOT_RELATIVE,
        authorization_sha256=world.manifest["authorization_sha256_at_freeze"])
    assert code_of(lambda: rm.verify_run_manifest(manifest, plan, repo_root=repo)) == "MANIFEST_SOURCE_COMMIT"


def test_the_environment_is_recorded_and_checked(world, monkeypatch):
    env = world.manifest["environment"]
    assert set(env["packages"]) == {"numpy", "scipy", "scikit-learn"} and env["python"]
    assert env == rm.current_environment()
    other = {**env, "packages": {**env["packages"], "numpy": "0.0.1"}}
    monkeypatch.setattr(rm, "current_environment", lambda: other)
    assert code_of(lambda: rm.verify_run_manifest(
        world.manifest, world.plan, repo_root=world.repo)) == "MANIFEST_ENVIRONMENT"
    rm.verify_run_manifest(world.manifest, world.plan, repo_root=world.repo, check_environment=False)
    bad = reseal({**world.manifest, "environment": {"python": "3"}})
    assert code_of(lambda: rm.verify_run_manifest(
        bad, world.plan, repo_root=world.repo, check_environment=False)) == "MANIFEST_ENVIRONMENT"


def test_the_authorization_hash_is_provenance_bound_but_not_checked_against_the_live_file(world):
    assert world.manifest["authorization_sha256_at_freeze"] == hashlib.sha256(
        PROTOCOLS["AUTHORIZATION-20261017-bank-development-repeats.md"]).hexdigest()
    # Only the decisions file is pinned by the binding.
    assert world.binding.protocol_review_sha256 == rm.protocol_review_digest(protocol_paths(world.repo))
    # The status document changes (checkboxes ticked): the manifest still verifies.
    authorization_path(world.repo).write_bytes(b"authorization v2 with ticked boxes\n")
    rm.verify_run_manifest(world.manifest, world.plan, repo_root=world.repo)
    # But the value is covered by the manifest digest.
    tampered = {**world.manifest, "authorization_sha256_at_freeze": "d" * 64}
    assert code_of(lambda: rm.verify_run_manifest(
        tampered, world.plan, repo_root=world.repo)) == "MANIFEST_DIGEST"


def test_the_manifest_must_be_inside_the_repo_tracked_and_unchanged(world, tmp_path):
    repo = world.repo
    outside = tmp_path / "outside.json"
    outside.write_bytes(rm.dump_manifest(world.manifest))
    assert code_of(lambda: rm.require_tracked_unmodified(repo, outside)) == "MANIFEST_OUTSIDE_REPO"
    inside = repo / rm.DEFAULT_MANIFEST_RELATIVE
    inside.parent.mkdir(parents=True)
    inside.write_bytes(rm.dump_manifest(world.manifest))
    assert code_of(lambda: rm.require_tracked_unmodified(repo, inside)) == "MANIFEST_UNTRACKED"
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "manifest")
    rm.require_tracked_unmodified(repo, inside)
    inside.write_bytes(rm.dump_manifest(world.manifest) + b" ")
    assert code_of(lambda: rm.require_tracked_unmodified(repo, inside)) == "MANIFEST_MODIFIED"


def test_gitattributes_keeps_the_manifest_json_lf():
    text = (Path(__file__).resolve().parents[2] / ".gitattributes").read_text(encoding="utf-8")
    assert "docs/research/*.json text eol=lf" in text.splitlines()


# ---------------------------------------------------------------- the scope is the import closure

def _reached_modules(root: Path) -> set[str]:
    """Repo-relative files of every shiftguard.* module reached by static imports."""
    import ast

    def module_file(dotted: str) -> Path | None:
        base = root.joinpath(*dotted.split("."))
        if (base / "__init__.py").is_file():
            return base / "__init__.py"
        return base.with_suffix(".py") if base.with_suffix(".py").is_file() else None

    pending = [*sorted((root / "shiftguard/repeats").glob("*.py")),
               *(root / name for name in rm.SOURCE_SCRIPTS)]
    seen: set[Path] = set()
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        seen.add(path)
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module] + [f"{node.module}.{alias.name}" for alias in node.names]
            for name in names:
                parts = name.split(".")
                if parts[0] != "shiftguard":
                    continue
                for end in range(1, len(parts) + 1):
                    target = module_file(".".join(parts[:end]))
                    if target is not None and target not in seen:
                        pending.append(target)
    return {path.relative_to(root).as_posix() for path in seen}


def test_every_module_the_run_imports_lies_in_the_source_scope():
    root = Path(__file__).resolve().parents[2]
    reached = _reached_modules(root)
    assert "shiftguard/repeats/run_manifest.py" in reached and "shiftguard/datasets/bank.py" in reached
    outside = sorted(path for path in reached if not rm.is_source_path(path))
    assert outside == []
    # The scope is narrower than the whole package: unrelated modules stay out.
    assert not rm.is_source_path("shiftguard/api/app.py")
    assert not rm.is_source_path("shiftguard/static/index.html")
    assert not rm.is_source_path("scripts/gate8_resource_preflight.py")
