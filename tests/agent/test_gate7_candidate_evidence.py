"""Negative probes for the candidate checker's source protection boundary."""
import hashlib
import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("gate7_checker", Path(__file__).resolve().parents[2] / "scripts/check_gate7_candidate.py")
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


def test_only_exact_provider_additions_reconstruct_recorded_settings():
    baseline = CHECKER.json.loads(CHECKER.BASELINE_SOURCE.read_text())
    source = (CHECKER.APP / "shiftguard/settings.py").read_bytes()
    assert CHECKER.authorized_settings_delta(source, baseline["files"]["shiftguard/settings.py"])


def test_unrelated_database_change_cannot_hide_in_authorized_delta():
    baseline = CHECKER.json.loads(CHECKER.BASELINE_SOURCE.read_text())
    source = (CHECKER.APP / "shiftguard/settings.py").read_bytes()
    changed = source.replace(b"MINIMUM_SQLITE_WAL_VERSION = (3, 51, 3)", b"MINIMUM_SQLITE_WAL_VERSION = (3, 0, 0)")
    assert changed != source
    assert not CHECKER.authorized_settings_delta(changed, baseline["files"]["shiftguard/settings.py"])


def test_default_on_thinking_cannot_pass_default_off_delta():
    source = (CHECKER.APP / "shiftguard/settings.py").read_bytes()
    baseline = CHECKER.json.loads(CHECKER.BASELINE_SOURCE.read_text())
    changed = source.replace(b"nebius_enable_thinking: bool = Field(\n        default=False", b"nebius_enable_thinking: bool = Field(\n        default=True")
    assert changed != source
    assert not CHECKER.authorized_settings_delta(changed, baseline["files"]["shiftguard/settings.py"])


def test_default_on_general_chat_cannot_pass_default_off_delta():
    source = (CHECKER.APP / "shiftguard/settings.py").read_bytes()
    baseline = CHECKER.json.loads(CHECKER.BASELINE_SOURCE.read_text())
    changed = source.replace(b"general_chat_enabled: bool = Field(\n        default=False", b"general_chat_enabled: bool = Field(\n        default=True")
    assert changed != source
    assert not CHECKER.authorized_settings_delta(changed, baseline["files"]["shiftguard/settings.py"])


def _app_factory_baseline():
    rows = CHECKER.protected_comparison()["files"]
    return next(row["baseline_sha256"] for row in rows if row["path"] == "shiftguard/api/main.py")


def test_only_exact_ordinary_chat_wiring_reconstructs_recorded_app_factory():
    source = (CHECKER.APP / "shiftguard/api/main.py").read_bytes()
    assert CHECKER.authorized_app_factory_delta(source, _app_factory_baseline())


def test_unrelated_app_factory_change_cannot_hide_in_ordinary_chat_delta():
    source = (CHECKER.APP / "shiftguard/api/main.py").read_bytes()
    baseline = _app_factory_baseline()
    for old, new in (
        (b"if injected_provider is not None and not test_harness:", b"if injected_provider is not None and False:"),
        (b"if not test_harness and (settings.agent_enabled or settings.general_chat_enabled):", b"if settings.agent_enabled or settings.general_chat_enabled:"),
        (b"        ordinary_budget.recover_unresolved()\n", b""),
        (b"    app.include_router(chat.router)\n", b"    app.include_router(chat.router)\n    app.include_router(chat.router)\n"),
        # Ownership bypass: recovery or dispatch without the exclusive owner.
        (b"            ordinary_owner.acquire()\n", b""),
        (b"OrdinaryBudget(engine, owner=ordinary_owner)", b"OrdinaryBudget(engine, owner=None)"),
        (b"                ordinary_owner.close()\n", b"                pass\n"),
        # Validation errors must not start echoing submitted input again.
        (b'"msg": str(error.get("msg", "Invalid value"))[:_MAX_ERROR_TEXT_CHARS],',
         b'"msg": str(error.get("msg", "Invalid value"))[:_MAX_ERROR_TEXT_CHARS], "input": error.get("input"),'),
        (b"_MAX_VALIDATION_ERRORS = 20\n", b"_MAX_VALIDATION_ERRORS = 2000\n"),
    ):
        changed = source.replace(old, new)
        assert changed != source
        assert not CHECKER.authorized_app_factory_delta(changed, baseline)


def test_actual_pinned_supplement_closes_configuration_hash_coverage():
    protected = CHECKER.protected_comparison()
    assert protected["status"] == "MATCH"
    assert protected["protected_contract_matches"] == 50
    assert protected["byte_identical_protected_contracts"] == 48
    assert protected["authorized_provider_only_deltas"] == 1
    assert protected["authorized_ordinary_chat_deltas"] == 2
    assert protected["applied_migration_matches"] == 11
    assert all(row["baseline_present"] for row in protected["files"])


def test_controller_and_renderer_are_bound_even_when_not_changed():
    bound = CHECKER.source_hashes()
    for path in ("shiftguard/agent/controller.py", "shiftguard/agent/registry.py", "shiftguard/agent/rendering.py"):
        assert bound[path] == hashlib.sha256((CHECKER.APP / path).read_bytes()).hexdigest()
