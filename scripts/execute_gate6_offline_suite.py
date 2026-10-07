"""Run Gate 6 offline checks and bind evidence to executed nodes and source bytes.

This command is for the parent after all scoped writers stop. It executes the
focused suites, frontend checks, browser suite and wheel smoke; it never runs a
live provider canary or installs dependencies.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
import zipfile
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parent.parent
VERIFICATION_ROOT = REPO_ROOT.parent / "verification" / "gate6"
PYTHON_EXE = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
NPM_CMD = r"C:\Program Files\nodejs\npm.cmd"
UV_PACKAGE_EXE = REPO_ROOT.parent / ".tools" / "uv-package" / "bin" / "uv.exe"
STATIC_ROOT = REPO_ROOT / "shiftguard" / "static"

# Node names below are declared permanent tests; browser names are actual spec
# titles. Backend obligations are attached only to cases that exercise persisted
# database semantics. S04/S06/S13 remain accepted controls.
_BOTH_DATABASES = ["sqlite", "postgresql"]


def _cases(
    positive: list[str],
    negative: list[str],
    *,
    database_nodes: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = [
        *({"node": node, "role": "positive"} for node in positive),
        *({"node": node, "role": "negative"} for node in negative),
    ]
    for case in cases:
        if case["node"] in database_nodes:
            case["backends"] = _BOTH_DATABASES.copy()
    return cases


def _browser_cases(positive: list[str], negative: list[str]) -> list[dict[str, str]]:
    return [
        *({"title": title, "role": "positive"} for title in positive),
        *({"title": title, "role": "negative"} for title in negative),
    ]


ACCEPTED_CONTROLS = {
    "G6-S04": "accepted in the correction review; preserved unchanged",
    "G6-S06": "accepted in the correction review; preserved unchanged",
    "G6-S13": "accepted in the correction review; preserved unchanged",
}

PROOF_CASES: dict[str, dict[str, Any]] = {
    "G6-S01": {"cases": _cases(
        ["test_luna_g6_protocol_recovers_the_saved_decision"],
        ["test_luna_g6_protocol_committed_tool_result_is_not_replayed_after_crash"],
        database_nodes=(
            "test_luna_g6_protocol_recovers_the_saved_decision",
            "test_luna_g6_protocol_committed_tool_result_is_not_replayed_after_crash",
        ),
    )},
    "G6-S02": {"cases": _cases(
        ["test_luna_g6_protocol_one_repair_reservation_survives_job_resume"],
        ["test_luna_g6_protocol_duplicate_provider_call_ids_fail_before_dispatch"],
        database_nodes=(
            "test_luna_g6_protocol_one_repair_reservation_survives_job_resume",
            "test_luna_g6_protocol_duplicate_provider_call_ids_fail_before_dispatch",
        ),
    )},
    "G6-S03": {"cases": _cases(
        ["test_luna_g6_protocol_queue_and_request_fence_rollback_together"],
        ["test_luna_g6_protocol_lost_lease_creates_no_trace_or_job", "test_luna_g6_protocol_revoked_session_at_queue_boundary_admits_nothing"],
        database_nodes=(
            "test_luna_g6_protocol_queue_and_request_fence_rollback_together",
            "test_luna_g6_protocol_lost_lease_creates_no_trace_or_job",
            "test_luna_g6_protocol_revoked_session_at_queue_boundary_admits_nothing",
        ),
    )},
    "G6-S05": {"cases": _cases(
        ["test_luna_g6_protocol_provider_turn_counter_is_reserved_before_await", "test_luna_g6_provider_p04_original_tool_call_id_preserved"],
        ["test_luna_g6_protocol_committed_tool_result_is_not_replayed_after_crash"],
        database_nodes=(
            "test_luna_g6_protocol_provider_turn_counter_is_reserved_before_await",
            "test_luna_g6_protocol_committed_tool_result_is_not_replayed_after_crash",
        ),
    )},
    "G6-S07": {"cases": _cases(
        ["test_luna_g6_protocol_recovers_the_saved_decision"],
        ["test_luna_g6_protocol_unissued_nonce_cannot_claim_or_replay", "test_luna_g6_protocol_nonce_from_future_generation_is_rejected"],
        database_nodes=(
            "test_luna_g6_protocol_recovers_the_saved_decision",
            "test_luna_g6_protocol_unissued_nonce_cannot_claim_or_replay",
            "test_luna_g6_protocol_nonce_from_future_generation_is_rejected",
        ),
    )},
    "G6-S08": {"cases": _cases(
        ["test_luna_g6_adhoc_enqueue_requires_current_session_authority"],
        ["test_luna_g6_protocol_session_revoked_during_provider_wait_blocks_dispatch", "test_luna_g6_protocol_capability_rotation_invalidates_saved_request"],
        database_nodes=(
            "test_luna_g6_adhoc_enqueue_requires_current_session_authority",
            "test_luna_g6_protocol_session_revoked_during_provider_wait_blocks_dispatch",
            "test_luna_g6_protocol_capability_rotation_invalidates_saved_request",
        ),
    )},
    "G6-S09": {"cases": _cases(
        ["test_luna_g6_authorized_reader_returns_strict_projection_without_private_metadata"],
        ["test_luna_g6_all_eight_readers_fail_closed_before_storage_lookup"],
        database_nodes=(
            "test_luna_g6_authorized_reader_returns_strict_projection_without_private_metadata",
            "test_luna_g6_all_eight_readers_fail_closed_before_storage_lookup",
        ),
    )},
    "G6-S10": {"cases": _cases(
        ["test_luna_g6_explanation_plan_is_strict_allowlisted_and_reference_bound"],
        ["test_luna_g6_valid_evidence_does_not_authorize_unchecked_provider_prose"],
    )},
    "G6-S11": {"cases": _cases(
        ["test_luna_g6_terminal_error_schema_canonicalizes_public_objects_and_legacy_strings", "test_luna_g6_project_tool_result_preserves_terminal_status_and_safe_code"],
        ["test_luna_g6_renderer_retains_sanitized_terminal_outcome_without_evidence"],
    )},
    "G6-S12": {"cases": _cases(
        ["test_luna_g6_failed_ninth_condition_and_all_sparse_diagnostics_are_retained"],
        ["test_luna_g6_incompatible_or_missing_identity_never_gets_improvement_direction", "test_luna_g6_protocol_terminal_job_error_survives_resume"],
        database_nodes=("test_luna_g6_protocol_terminal_job_error_survives_resume",),
    )},
    "G6-S14": {"cases": _cases(
        ["test_luna_g6_typed_cost_error_and_null_loss_keep_condition_reference"],
        ["test_luna_g6_comparison_requires_bound_predictor_identity"],
        database_nodes=("test_luna_g6_comparison_requires_bound_predictor_identity",),
    )},
    "G6-S15": {"cases": _cases(
        ["test_luna_g6_explanation_plan_is_strict_allowlisted_and_reference_bound", "test_luna_g6_summary_default_and_semantic_allowlists_match"],
        ["test_luna_g6_safe_argument_preparation_drops_rejected_values"],
    )},
    "G6-S16": {"cases": _cases(
        ["test_luna_g6_run_projection_rebuilds_notes_from_safe_job_fields", "test_luna_g6_authorized_reader_returns_strict_projection_without_private_metadata"],
        ["test_luna_g6_error_projection_never_echoes_private_input_or_nested_config"],
        database_nodes=("test_luna_g6_authorized_reader_returns_strict_projection_without_private_metadata",),
    )},
    "G6-S17": {"cases": _cases(
        ["test_luna_g6_provider_p04_output_cap_and_transcript_shape_bounds"],
        ["test_luna_g6_safe_argument_preparation_drops_rejected_values", "test_luna_g6_protocol_provider_output_bounds_fail_closed"],
        database_nodes=("test_luna_g6_protocol_provider_output_bounds_fail_closed",),
    )},
    "G6-S18": {"cases": _cases(
        ["test_luna_g6_protocol_terminal_commit_and_receipt_are_one_transaction"],
        ["test_luna_g6_protocol_completed_job_without_publication_is_not_evidence", "test_luna_g6_protocol_terminal_job_error_survives_resume"],
        database_nodes=(
            "test_luna_g6_protocol_terminal_commit_and_receipt_are_one_transaction",
            "test_luna_g6_protocol_completed_job_without_publication_is_not_evidence",
            "test_luna_g6_protocol_terminal_job_error_survives_resume",
        ),
    )},
    "G6-P01": {"browser_cases": _browser_cases(
        [
            "[simulated] transport loss after real acceptance reloads the original intent and retries the same API identity",
            "actual WAITING request is rehydrated on reload with its job and server continuation identity",
        ],
        [
            "Clear suppresses a delayed response after the real queue accepted the original POST",
            "agent intent storage failure is visible and prevents an unsaved POST",
        ],
    )},
    "G6-P02": {"browser_cases": _browser_cases(
        ["[simulated] actual accepted work remains bound to its expired session until an explicit reconnect"],
        [
            "[simulated] capability rejection Clear does not replace the expired authority",
            "[simulated] terminal API response renders structured and legacy tool errors safely",
        ],
    )},
    "G6-P03": {"cases": _cases(
        ["test_luna_g6_preflight_p03_positive", "test_luna_g6_preflight_p03_provider_supplied_fallback_fails_required_plan"],
        [
            "test_luna_g6_preflight_p03_one_token_no_wire",
            "test_luna_g6_preflight_p03_unknown_usage_stops",
            "test_luna_g6_preflight_p03_exact_ping_required",
            "test_luna_g6_preflight_p03_exact_model_required",
            "test_luna_g6_preflight_p03_tool_arguments_required",
            "test_luna_g6_preflight_p03_original_id_exchange_required",
            "test_luna_g6_preflight_p03_plan_or_fallback_required",
            "test_luna_g6_preflight_p03_call_allowance_stops",
            "test_luna_g6_preflight_p03_sdk_429_is_single_wire_attempt",
        ],
    )},
    "G6-P04": {"cases": _cases(
        ["test_luna_g6_provider_p04_positive_actual_sdk_roundtrip", "test_luna_g6_provider_p04_original_tool_call_id_preserved"],
        [
            "test_luna_g6_provider_p04_configured_key_never_reaches_error_or_log",
            "test_luna_g6_provider_p04_empty_choices_is_typed",
            "test_luna_g6_provider_p04_actual_sdk_error_classification",
            "test_luna_g6_provider_p04_output_cap_and_transcript_shape_bounds",
            "test_luna_g6_provider_p04_settings_reject_unbounded_values",
        ],
    )},
    "G6-P05": {"cases": _cases(
        [
            "test_upgrade_database_from_isolated_working_directory",
            "test_migration_resources_exist_in_package",
            "test_luna_g6_protocol_recovers_the_saved_decision",
        ],
        ["test_luna_g6_protocol_migration_preserves_nonempty_historical_0009", "test_luna_g6_protocol_migration_repairs_expanded_0009_shape"],
        database_nodes=("test_luna_g6_protocol_recovers_the_saved_decision",),
    )},
    "G6-P06": {"cases": _cases(
        ["test_luna_g6_evidence_p06_positive_real_nodes", "test_luna_g6_evidence_p06_collection_nodes_match_declared_count"],
        [
            "test_luna_g6_evidence_p06_junit_skips_and_missing_nodes_rejected",
            "test_luna_g6_evidence_p06_junit_count_mismatch_rejected",
            "test_luna_g6_evidence_p06_playwright_recursive_and_skip_rejected",
            "test_luna_g6_evidence_p06_wrong_backend_and_missing_finding_rejected",
            "test_luna_g6_evidence_p06_source_drift_and_package_origin_rejected",
            "test_luna_g6_evidence_p06_failed_canary_node_rejected",
        ],
    )},
    "G6-P07": {"cases": _cases(
        [
            "test_luna_g6_startup_p07_positive_explicit_harness_labeled",
            "test_luna_g6_startup_p07_positive_harness_accepts_explicit_script",
            "test_luna_g6_startup_scenario_skips_cross_session_backlog_until_bound_job_claim",
        ],
        [
            "test_luna_g6_startup_p07_negative_local_disabled",
            "test_luna_g6_startup_p07_negative_hosted_disabled",
            "test_luna_g6_startup_p07_test_flags_rejected",
            "test_luna_g6_startup_p07_injected_provider_rejected",
            "test_luna_g6_startup_p07_negative_harness_rejects_unapproved_provider",
        ],
    )},
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(65536):
            digest.update(chunk)
    return digest.hexdigest()


def _junit_node_id(case: ET.Element) -> str | None:
    name = case.attrib.get("name")
    if not name:
        return None
    classname = case.attrib.get("classname", "")
    if not classname:
        return name
    parts = classname.split(".")
    module_parts = []
    class_parts = []
    for part in parts:
        if class_parts or (part and part[:1].isupper()):
            class_parts.append(part)
        else:
            module_parts.append(part)
    module = "/".join(module_parts)
    if module and not module.endswith(".py"):
        module += ".py"
    suffix = "::".join([*class_parts, name])
    return f"{module}::{suffix}" if module else suffix


def parse_junit_xml(junit_file: Path) -> dict[str, Any]:
    """Validate declared counters against all actual testcase nodes recursively."""
    if not junit_file.is_file():
        return {"status": "FAIL", "error": "REPORT_MISSING", "tests": 0, "failures": 0, "errors": 0, "skipped": 0, "nodes": []}
    try:
        root = ET.parse(junit_file).getroot()
    except (ET.ParseError, OSError) as exc:
        return {"status": "FAIL", "error": f"REPORT_INVALID:{type(exc).__name__}", "tests": 0, "failures": 0, "errors": 0, "skipped": 0, "nodes": []}
    cases = list(root.iter("testcase"))
    nodes: list[dict[str, str]] = []
    failure_count = error_count = skipped_count = rerun_count = 0
    malformed = False
    seen: set[str] = set()
    for case in cases:
        node_id = _junit_node_id(case)
        if not node_id or node_id in seen:
            malformed = True
            node_id = node_id or f"<missing-node-{len(nodes)}>"
        seen.add(node_id)
        failures = list(case.iter("failure"))
        errors = list(case.iter("error"))
        skipped = list(case.iter("skipped"))
        reruns = list(case.iter("rerun")) + list(case.iter("flakyFailure"))
        failure_count += bool(failures)
        error_count += bool(errors)
        skipped_count += bool(skipped)
        rerun_count += bool(reruns)
        outcome = "failed" if failures else "error" if errors else "skipped" if skipped else "passed"
        if reruns:
            outcome = "flaky"
        nodes.append({"node_id": node_id, "outcome": outcome})

    counter_errors: list[str] = []
    for suite in root.iter("testsuite"):
        suite_cases = list(suite.iter("testcase"))
        actual = {
            "tests": len(suite_cases),
            "failures": sum(bool(list(case.iter("failure"))) for case in suite_cases),
            "errors": sum(bool(list(case.iter("error"))) for case in suite_cases),
            "skipped": sum(bool(list(case.iter("skipped"))) for case in suite_cases),
        }
        for key, value in actual.items():
            declared = suite.attrib.get(key)
            if declared is not None:
                try:
                    if int(declared) != value:
                        counter_errors.append(f"{key}:{declared}!={value}")
                except ValueError:
                    counter_errors.append(f"{key}:not-integer")
    if root.tag == "testsuites":
        for key, actual in (("tests", len(cases)), ("failures", failure_count), ("errors", error_count), ("skipped", skipped_count)):
            declared = root.attrib.get(key)
            if declared is not None:
                try:
                    if int(declared) != actual:
                        counter_errors.append(f"root-{key}:{declared}!={actual}")
                except ValueError:
                    counter_errors.append(f"root-{key}:not-integer")
    status = "PASS" if cases and not malformed and not counter_errors and not failure_count and not error_count and not skipped_count and not rerun_count else "FAIL"
    return {
        "status": status,
        "tests": len(cases),
        "failures": failure_count,
        "errors": error_count,
        "skipped": skipped_count,
        "flaky": rerun_count,
        "nodes": nodes,
        "counter_errors": counter_errors,
        "malformed_nodes": malformed,
    }


def parse_playwright_json(report_file: Path) -> dict[str, Any]:
    """Count complete nested Playwright test trees and reconcile their stats."""
    if not report_file.is_file():
        return {"status": "FAIL", "error": "REPORT_MISSING", "tests": 0, "nodes": []}
    try:
        report = json.loads(report_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "FAIL", "error": f"REPORT_INVALID:{type(exc).__name__}", "tests": 0, "nodes": []}
    if not isinstance(report, dict) or not isinstance(report.get("suites"), list):
        return {"status": "FAIL", "error": "SUITE_TREE_MISSING", "tests": 0, "nodes": []}
    config = report.get("config")
    metadata = config.get("metadata") if isinstance(config, dict) else None
    metadata_valid = (
        isinstance(metadata, dict)
        and metadata.get("providerKind") == "scripted-test-harness"
        and metadata.get("evidenceMode") == "scripted"
        and metadata.get("liveProviderCalls") is False
    )
    nodes: list[dict[str, str]] = []
    malformed = False

    def visit_suite(suite: Any, parents: tuple[str, ...] = ()) -> None:
        nonlocal malformed
        if not isinstance(suite, dict):
            malformed = True
            return
        suite_title = suite.get("title", "")
        next_parents = parents + ((suite_title,) if isinstance(suite_title, str) and suite_title else ())
        specs = suite.get("specs", [])
        children = suite.get("suites", [])
        if not isinstance(specs, list) or not isinstance(children, list):
            malformed = True
            return
        for spec in specs:
            if not isinstance(spec, dict) or not isinstance(spec.get("tests"), list):
                malformed = True
                continue
            spec_title = spec.get("title", "")
            for test in spec["tests"]:
                if not isinstance(test, dict) or not isinstance(test.get("results"), list) or not test["results"]:
                    malformed = True
                    continue
                test_title = test.get("title", "")
                title = " ".join(str(part) for part in (*next_parents, spec_title, test_title) if part)
                declared_status = test.get("status")
                results = test["results"]
                raw_statuses = [entry.get("status") for entry in results if isinstance(entry, dict)]
                if len(raw_statuses) != len(results):
                    malformed = True
                if declared_status in ("expected", "passed") and all(value == "passed" for value in raw_statuses):
                    outcome = "passed"
                elif declared_status in ("skipped",) or all(value == "skipped" for value in raw_statuses):
                    outcome = "skipped"
                elif declared_status == "flaky" or ("passed" in raw_statuses and any(value != "passed" for value in raw_statuses)):
                    outcome = "flaky"
                else:
                    outcome = "failed"
                if not title:
                    malformed = True
                nodes.append({"title": title, "outcome": outcome})
        for child in children:
            visit_suite(child, next_parents)

    for suite in report["suites"]:
        visit_suite(suite)
    counts = {
        "expected": sum(node["outcome"] == "passed" for node in nodes),
        "unexpected": sum(node["outcome"] in ("failed", "flaky") for node in nodes),
        "skipped": sum(node["outcome"] == "skipped" for node in nodes),
        "flaky": sum(node["outcome"] == "flaky" for node in nodes),
        "total": len(nodes),
    }
    stat_errors: list[str] = []
    stats = report.get("stats")
    if not isinstance(stats, dict):
        stat_errors.append("stats-missing")
    else:
        for required in ("expected", "unexpected", "skipped", "flaky"):
            if required not in stats:
                stat_errors.append(f"stats-{required}-missing")
        aliases = {"expected": "expected", "unexpected": "unexpected", "skipped": "skipped", "flaky": "flaky", "total": "total"}
        for key, target in aliases.items():
            declared = stats.get(key)
            if declared is not None and declared != counts[target]:
                stat_errors.append(f"stats-{key}:{declared}!={counts[target]}")
    status = "PASS" if nodes and metadata_valid and not malformed and not stat_errors and counts["unexpected"] == 0 and counts["skipped"] == 0 else "FAIL"
    return {
        "status": status,
        "tests": len(nodes),
        **counts,
        "nodes": nodes,
        "malformed": malformed,
        "stat_errors": stat_errors,
        "scripted_metadata_valid": metadata_valid,
    }


def _backend_for_node(node_id: str) -> str | None:
    # Fixture IDs may combine the backend with a second parameter, for example
    # [postgresql-before_dispatch]. Match only an exact leading token after '['.
    for token, backend in (("postgresql", "postgresql"), ("postgres", "postgresql"), ("sqlite", "sqlite")):
        if re.search(rf"\[{token}(?=[\],-])", node_id, flags=re.IGNORECASE):
            return backend
    return None


def derive_proof_map(
    junit_reports: list[dict[str, Any]],
    browser_report: dict[str, Any],
    requirements: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    requirements = PROOF_CASES if requirements is None else requirements
    nodes = [node for report in junit_reports for node in report.get("nodes", [])]
    browser_nodes = browser_report.get("nodes", [])
    findings: dict[str, Any] = {}
    for finding, requirement in requirements.items():
        proof_nodes: list[dict[str, str]] = []
        missing: list[str] = []
        missing_backend_cases: list[str] = []
        missing_obligations: list[str] = []
        observed_roles: set[str] = set()
        required_backends: set[str] = set()
        observed_backends: set[str] = set()
        failed_case = False
        for case in requirement.get("cases", []):
            token = case["node"]
            role = case["role"]
            case_backends = case.get("backends", requirement.get("backends", []))
            required_backends.update(case_backends)
            matched = [node for node in nodes if _node_matches_token(node["node_id"], token)]
            if not matched:
                missing.append(token)
                missing_obligations.append(f"{role} case requires collected node {token}")
            elif any(node["outcome"] != "passed" for node in matched):
                failed_case = True
                missing_obligations.append(f"{role} case did not pass: {token}")
            else:
                observed_roles.add(role)
            for backend in case_backends:
                backend_matches = [node for node in matched if _backend_for_node(node["node_id"]) == backend]
                if not backend_matches:
                    missing_backend_cases.append(f"{token}[{backend}]")
                    missing_obligations.append(f"{role} case requires passed {backend} node {token}")
                elif any(node["outcome"] != "passed" for node in backend_matches):
                    failed_case = True
                    missing_obligations.append(f"{role} case has a failing {backend} node: {token}")
                else:
                    observed_backends.add(backend)
            proof_nodes.extend({**node, "role": role} for node in matched)
        for case in requirement.get("browser_cases", []):
            title_token = case["title"]
            role = case["role"]
            matched = [node for node in browser_nodes if title_token in node["title"]]
            if not matched:
                missing.append(title_token)
                missing_obligations.append(f"{role} browser case requires actual title {title_token}")
            elif any(node["outcome"] != "passed" for node in matched):
                failed_case = True
                missing_obligations.append(f"{role} browser case did not pass: {title_token}")
            else:
                observed_roles.add(role)
            proof_nodes.extend({"node_id": item["title"], "outcome": item["outcome"], "role": role} for item in matched)
        required_roles = set(requirement.get("required_roles", ["positive", "negative"]))
        missing_roles = sorted(required_roles - observed_roles)
        missing_obligations.extend(f"required {role} coverage has no passing mapped case" for role in missing_roles)
        required_backend_list = sorted(required_backends)
        observed_backend_list = sorted(observed_backends)
        absent_backends = [backend for backend in required_backend_list if backend not in observed_backends]
        if absent_backends:
            missing_obligations.extend(f"finding requires backend coverage: {backend}" for backend in absent_backends)
        finding_status = "FAILED" if failed_case else "BLOCKED" if missing_obligations else "PROVEN"
        findings[finding] = {
            "status": finding_status,
            "proof_nodes": proof_nodes,
            "missing_cases": missing,
            "missing_backend_cases": missing_backend_cases,
            "missing_obligations": missing_obligations,
            "missing_roles": missing_roles,
            "required_backends": required_backend_list,
            "observed_backends": observed_backend_list,
            "missing_backends": absent_backends,
        }
    for finding, basis in ACCEPTED_CONTROLS.items():
        findings[finding] = {"status": "ACCEPTED_CONTROL", "basis": basis, "proof_nodes": []}
    statuses = [value["status"] for value in findings.values() if value["status"] != "ACCEPTED_CONTROL"]
    overall = "FAILED" if "FAILED" in statuses else "BLOCKED" if "BLOCKED" in statuses else "PROVEN" if statuses else "BLOCKED"
    return {"findings": findings, "status": overall}


def _node_matches_token(node_id: str, token: str) -> bool:
    """Match the full pytest function name, allowing only its parameter suffix."""
    function_name = node_id.rsplit("::", 1)[-1]
    return function_name == token or function_name.startswith(token + "[")


def package_origins_valid(origins: dict[str, str], extracted_root: Path) -> bool:
    root = extracted_root.resolve()
    if not origins:
        return False
    for origin in origins.values():
        try:
            Path(origin).resolve().relative_to(root)
        except (OSError, ValueError):
            return False
    return True


def source_snapshots_match(before: dict[str, Any], after: dict[str, Any]) -> bool:
    return bool(before.get("available") and after.get("available") and before.get("files") == after.get("files"))


def is_mutable_slice_path(path: str) -> bool:
    exact = {
        "shiftguard/agent/provider.py",
        "shiftguard/settings.py",
        "shiftguard/api/main.py",
        "shiftguard/api/test_harness.py",
        "shiftguard/api/routes/agent_requests.py",
        "shiftguard/jobs/queue.py",
        "frontend/playwright.config.ts",
        "frontend/scripts/e2e-server.py",
        "frontend/src/App.tsx",
        "frontend/src/styles.css",
        "frontend/src/api/agent.ts",
        "frontend/src/hooks/useAgent.ts",
        "frontend/src/components/AgentPanel.tsx",
        "tests/e2e/test_agent_flow.spec.ts",
        "tests/unit/test_migrations_isolation.py",
        "tests/agent/test_provider.py",
    }
    scripts = {"scripts/preflight_nebius.py", "scripts/execute_gate6_offline_suite.py", "scripts/agent_test_harness.py"}
    owned_test = re.fullmatch(r"tests/agent/test_luna_g6_(?:preflight|evidence|startup|provider)[A-Za-z0-9_]*\.py", path)
    return path in exact or path in scripts or owned_test is not None


def protected_file_hashes(snapshot: dict[str, Any]) -> dict[str, str]:
    return {path: digest for path, digest in snapshot.get("files", {}).items() if not is_mutable_slice_path(path)}


def playwright_output_matches(output: str, report: dict[str, Any]) -> bool:
    summary_lines = [
        line.strip() for line in output.splitlines()
        if re.search(r"\b(?:passed|failed|skipped|flaky|timed out)\b", line, re.IGNORECASE)
        and re.search(r"\d+\s+(?:passed|failed|skipped|flaky|timed out)", line, re.IGNORECASE)
    ]
    if not summary_lines:
        return False
    line = summary_lines[-1]
    parsed = {"passed": 0, "failed": 0, "skipped": 0, "flaky": 0, "timed out": 0}
    for count, kind in re.findall(r"(\d+)\s+(passed|failed|skipped|flaky|timed out)", line, re.IGNORECASE):
        parsed[kind.lower()] += int(count)
    return (
        parsed["passed"] == report.get("expected", -1)
        and parsed["failed"] + parsed["flaky"] + parsed["timed out"] == report.get("unexpected", -1)
        and parsed["skipped"] == report.get("skipped", -1)
        and sum(parsed.values()) == report.get("tests", -1)
    )


def source_snapshot() -> dict[str, Any]:
    git_args = ["git", "-c", f"safe.directory={REPO_ROOT.as_posix()}", "ls-files", "--cached", "--others", "--exclude-standard", "-z"]
    listing = subprocess.run(git_args, cwd=REPO_ROOT, capture_output=True)
    if listing.returncode != 0:
        return {"available": False, "error": f"git-ls-files-exit-{listing.returncode}", "files": {}}
    paths = sorted({entry.decode("utf-8", "surrogateescape").replace("\\", "/") for entry in listing.stdout.split(b"\0") if entry})
    hashes: dict[str, str] = {}
    missing: list[str] = []
    for rel in paths:
        path = REPO_ROOT / Path(rel)
        if path.is_file():
            hashes[rel] = sha256_file(path)
        else:
            hashes[rel] = "<MISSING>"
            missing.append(rel)
    return {"available": True, "files": hashes, "missing": missing}


def _git_state() -> dict[str, Any]:
    prefix = ["git", "-c", f"safe.directory={REPO_ROOT.as_posix()}"]
    head = subprocess.run([*prefix, "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True)
    status = subprocess.run([*prefix, "status", "--porcelain"], cwd=REPO_ROOT, capture_output=True, text=True)
    ok = head.returncode == 0 and status.returncode == 0
    return {
        "available": ok,
        "head_exit": head.returncode,
        "status_exit": status.returncode,
        "head": head.stdout.strip() if head.returncode == 0 else None,
        "dirty": bool(status.stdout.strip()) if status.returncode == 0 else None,
    }


def _postgres_environment(env: dict[str, str]) -> dict[str, Any]:
    command = ". '..\\.tools\\use-existing-test-postgres.ps1'; [Console]::Write($env:SHIFTGUARD_TEST_POSTGRES_URL)"
    result = subprocess.run(["powershell", "-NoProfile", "-Command", command], cwd=REPO_ROOT, capture_output=True, text=True)
    candidates = [line.strip() for line in result.stdout.splitlines()
                  if re.fullmatch(r"postgresql\+psycopg://\S+", line.strip())]
    if result.returncode == 0 and len(candidates) == 1:
        env["SHIFTGUARD_TEST_POSTGRES_URL"] = candidates[0]
        return {"status": "AVAILABLE", "helper_exit": result.returncode, "url_redacted": True}
    blocker = "helper did not return a PostgreSQL URL"
    for line in (result.stderr + "\n" + result.stdout).splitlines():
        if re.search(r"access is denied|permission denied|WSL.*denied|not recognized|cannot be loaded", line, re.IGNORECASE):
            blocker = re.sub(r"postgres(?:ql)?[^\s]*", "PostgreSQL endpoint", line, flags=re.IGNORECASE)[:240]
            break
    return {"status": "BLOCKED", "helper_exit": result.returncode, "blocker": blocker, "url_redacted": True}


def _safe_output(output: str, env: dict[str, str]) -> str:
    postgres_url = env.get("SHIFTGUARD_TEST_POSTGRES_URL")
    if postgres_url:
        output = output.replace(postgres_url, "[REDACTED_POSTGRES_URL]")
    return re.sub(
        r"postgres(?:ql)?(?:\+psycopg)?://[^\s'\"\]]+",
        lambda match: "[REDACTED_POSTGRES_URL:" + hashlib.sha256(match.group(0).encode()).hexdigest()[:16] + "]",
        output, flags=re.IGNORECASE,
    )


def run_cmd(args: list[str], env: dict[str, str], log_file: Path, *, shell: bool = False) -> tuple[int, str]:
    started = time.monotonic()
    completed = subprocess.run(args, cwd=REPO_ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", shell=shell)
    output = _safe_output(completed.stdout + completed.stderr, env)
    log_file.write_text(output, encoding="utf-8", newline="\n")
    print(f"{Path(str(args[0])).name}: exit {completed.returncode}, {time.monotonic() - started:.1f}s")
    return completed.returncode, output


def _pytest_command(paths: list[str], attempt: Path, report: Path) -> list[str]:
    temp = Path(tempfile.mkdtemp(prefix="shiftguard-g6-"))
    return [str(PYTHON_EXE), "-B", "-m", "pytest", *paths, "-q", "-p", "no:cacheprovider", "--basetemp", str(temp), "--junitxml", str(report), "--tb=short"]


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _collect_node_ids(output: str) -> tuple[list[str], int | None]:
    node_ids = []
    summary_count: int | None = None
    for line in output.splitlines():
        stripped = line.strip()
        if "::" in stripped and not stripped.startswith("="):
            node_ids.append(stripped)
        match = re.search(r"\b(\d+)\s+tests? collected\b", stripped)
        if match:
            summary_count = int(match.group(1))
    return node_ids, summary_count


def collection_output_valid(output: str, exit_code: int) -> tuple[bool, list[str], int | None]:
    node_ids, summary_count = _collect_node_ids(output)
    valid = exit_code == 0 and bool(node_ids) and summary_count == len(node_ids) and len(set(node_ids)) == len(node_ids)
    return valid, node_ids, summary_count


def _write_proof_outputs(attempt: Path, proof: dict[str, Any], digest: str, commands: dict[str, Any]) -> None:
    enriched = {
        "batch": "LUNA6-G6-MAJOR-01",
        "attempt_id": attempt.name,
        "source_digest_before": digest,
        "commands": commands,
        **proof,
    }
    _write_json(attempt / "corrections-proof-map.json", enriched)
    _write_json(attempt / "contract-evidence.json", {
        "batch": "LUNA6-G6-MAJOR-01",
        "attempt_id": attempt.name,
        "source_digest_before": digest,
        "findings": proof["findings"],
        "proof_status": proof["status"],
        "commands": commands,
    })


def main() -> int:
    attempt = VERIFICATION_ROOT / f"offline-luna-major-{uuid4()}"
    attempt.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8", OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", NUMEXPR_NUM_THREADS="1")
    env["SG_GATE5_ATTEMPT_DIR"] = str(attempt)
    env.pop("SG_E2E_BASE_URL", None)
    env.pop("NEBIUS_API_KEY", None)
    env.pop("SHIFTGUARD_AGENT_PROVIDER_MODE", None)
    env.pop("SHIFTGUARD_ALLOW_TEST_SCRIPTED_PROVIDER", None)
    env["SHIFTGUARD_AGENT_ENABLED"] = "false"

    before = source_snapshot()
    git_before = _git_state()
    started = time.time()
    postgres = _postgres_environment(env)
    commands: dict[str, Any] = {}

    def run(name: str, args: list[str], *, shell: bool = False) -> str:
        code, output = run_cmd(args, env, attempt / f"{name}.log", shell=shell)
        commands[name] = {"exit_code": code, "argv": args, "status": "PASS" if code == 0 else "FAIL"}
        return output

    reports = {
        "agent": attempt / "agent-junit.xml",
        "static": attempt / "static-junit.xml",
        "migrations": attempt / "migrations-junit.xml",
    }
    focused_paths = {
        "agent": ["tests/agent"],
        "static": ["tests/integration/test_static_boundaries.py"],
        "migrations": ["tests/unit/test_migrations_isolation.py"],
    }
    for name, paths in focused_paths.items():
        run(name, _pytest_command(paths, attempt, reports[name]))

    collect_log = attempt / "collection.log"
    collect_temp = Path(tempfile.mkdtemp(prefix="shiftguard-g6-collect-"))
    collect_args = [str(PYTHON_EXE), "-B", "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", "--basetemp", str(collect_temp)]
    code_collect, collect_output = run_cmd(collect_args, env, collect_log)
    commands["collection"] = {"exit_code": code_collect, "argv": collect_args, "status": "PASS" if code_collect == 0 else "FAIL"}
    collection_valid, collected_nodes, collected_summary = collection_output_valid(collect_output, code_collect)
    _write_json(attempt / "pytest-collection.json", {
        "status": "PASS" if collection_valid else "FAIL",
        "summary_count": collected_summary,
        "actual_node_count": len(collected_nodes),
        "unique_node_count": len(set(collected_nodes)),
        "node_ids": collected_nodes,
    })

    run("typecheck", [NPM_CMD, "--prefix", "frontend", "run", "typecheck"], shell=True)
    # Vite writes to the attempt directory so this runner cannot regenerate or
    # overwrite the protected package's static assets.
    frontend_build = attempt / "frontend-build"
    frontend_build.mkdir()
    run("build", [NPM_CMD, "--prefix", "frontend", "exec", "--", "vite", "build", "frontend", "--config", "frontend/vite.config.ts", "--configLoader", "native", "--outDir", str(frontend_build), "--emptyOutDir"], shell=True)
    browser_output = run("browser", [NPM_CMD, "--prefix", "frontend", "run", "test:e2e"], shell=True)
    offline_evidence = attempt / "preflight-offline.json"
    run("preflight_offline", [str(PYTHON_EXE), "scripts/preflight_nebius.py", "--write-redacted-evidence", str(offline_evidence)])

    wheel_dir = attempt / "wheels"
    wheel_dir.mkdir()
    wheel_code = run("package_build", [str(UV_PACKAGE_EXE), "build", "--wheel", "--out-dir", str(wheel_dir)])
    wheels = list(wheel_dir.glob("*.whl"))
    package: dict[str, Any] = {"status": "FAIL", "wheel_count": len(wheels), "origin_valid": False}
    package_code = 1
    if commands["package_build"]["exit_code"] == 0 and len(wheels) == 1:
        extracted = attempt / "wheel-extracted"
        extracted.mkdir()
        try:
            with zipfile.ZipFile(wheels[0]) as archive:
                names = archive.namelist()
                archive.extractall(extracted)
            required_members = {
                "shiftguard/api/test_harness.py",
                "shiftguard/agent/provider.py",
            }
            migration_members = [name for name in names if Path(name).name.startswith("0010_") and name.endswith(".py")]
            member_ok = all(name in names for name in required_members) and len(migration_members) == 1
            expected_head = Path(migration_members[0]).stem if migration_members else None
            smoke_dir = attempt / "wheel-run"
            smoke_dir.mkdir()
            sqlite_path = (smoke_dir / "wheel-smoke.sqlite").as_posix()
            smoke_code = (
                "import json, pathlib, shiftguard, shiftguard.agent.provider, shiftguard.api.main, shiftguard.api.test_harness; "
                "from sqlalchemy import text; from shiftguard.settings import Settings; from shiftguard.migrations import upgrade_database; "
                "from shiftguard.storage.db import create_engine_for_settings; "
                "s=Settings(db_url='sqlite:///" + sqlite_path + "', artifact_root=pathlib.Path('artifacts'), _env_file=None); "
                "upgrade_database(s); "
                "e=create_engine_for_settings(s); "
                "revision=e.connect().execute(text('SELECT version_num FROM alembic_version')).scalar_one(); e.dispose(); "
                "print(json.dumps({'shiftguard':shiftguard.__file__,'provider':shiftguard.agent.provider.__file__,'api':shiftguard.api.main.__file__,'harness':shiftguard.api.test_harness.__file__,'revision':revision}))"
            )
            smoke_env = env.copy()
            smoke_env["PYTHONPATH"] = str(extracted)
            smoke_env["SHIFTGUARD_DB_URL"] = f"sqlite:///{sqlite_path}"
            smoke_env["SHIFTGUARD_ARTIFACT_ROOT"] = str(smoke_dir / "artifacts")
            smoke = subprocess.run([str(PYTHON_EXE), "-B", "-c", smoke_code], cwd=smoke_dir, env=smoke_env, capture_output=True, text=True, encoding="utf-8", errors="replace")
            output = _safe_output(smoke.stdout + smoke.stderr, smoke_env)
            (attempt / "package-smoke.log").write_text(output, encoding="utf-8", newline="\n")
            try:
                origins = json.loads(smoke.stdout.strip().splitlines()[-1])
            except (IndexError, json.JSONDecodeError):
                origins = {}
            origin_modules = {name: value for name, value in origins.items() if name != "revision"}
            origin_ok = package_origins_valid(origin_modules, extracted)
            migration_ok = origins.get("revision") == expected_head
            package_ok = smoke.returncode == 0 and member_ok and origin_ok and migration_ok
            package_code = 0 if package_ok else 1
            package = {
                "status": "PASS" if package_ok else "FAIL",
                "wheel": wheels[0].name,
                "member_count": len(names),
                "required_members_present": member_ok,
                "module_origins": origins,
                "origin_valid": origin_ok,
                "runtime_migration_head_valid": migration_ok,
                "smoke_exit": smoke.returncode,
            }
        except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
            package["error_type"] = type(exc).__name__
    commands["package_smoke"] = {"exit_code": package_code, "status": "PASS" if package_code == 0 else "FAIL"}
    _write_json(attempt / "package-smoke.json", package)

    junit = [parse_junit_xml(path) for path in reports.values()]
    browser = parse_playwright_json(attempt / "playwright-report.json")
    browser_output_valid = playwright_output_matches(browser_output, browser)
    proof = derive_proof_map(junit, browser)
    after = source_snapshot()
    git_after = _git_state()
    source_unchanged = source_snapshots_match(before, after)
    git_ok = git_before.get("available") and git_after.get("available")
    protected_before = protected_file_hashes(before)
    protected_after = protected_file_hashes(after)
    protected_unchanged = protected_before == protected_after
    static_before = {path: digest for path, digest in before.get("files", {}).items() if path.startswith("shiftguard/static/")}
    static_after = {path: digest for path, digest in after.get("files", {}).items() if path.startswith("shiftguard/static/")}
    static_unchanged = static_before == static_after
    docs_before = {path: digest for path, digest in before.get("files", {}).items() if path.startswith("docs/")}
    docs_after = {path: digest for path, digest in after.get("files", {}).items() if path.startswith("docs/")}
    docs_unchanged = docs_before == docs_after
    manifest_before = hashlib.sha256(json.dumps(before.get("files", {}), sort_keys=True).encode()).hexdigest()
    manifest_after = hashlib.sha256(json.dumps(after.get("files", {}), sort_keys=True).encode()).hexdigest()
    _write_json(attempt / "source-manifest.json", {
        "attempt_id": attempt.name,
        "batch": "LUNA6-G6-MAJOR-01",
        "captured_before_tests": started,
        "git_before": git_before,
        "git_after": git_after,
        "file_count_before": len(before.get("files", {})),
        "file_count_after": len(after.get("files", {})),
        "source_digest_before": manifest_before,
        "source_digest_after": manifest_after,
        "file_hashes_before": before.get("files", {}),
        "file_hashes_after": after.get("files", {}),
        "source_unchanged": bool(source_unchanged),
        "protected_unchanged": protected_unchanged,
        "protected_files": sorted(protected_before),
        "generated_static_unchanged": static_unchanged,
        "generated_static_before": static_before,
        "generated_static_after": static_after,
        "final_documents_unchanged": docs_unchanged,
        "documents_digest_before": hashlib.sha256(json.dumps(docs_before, sort_keys=True).encode()).hexdigest(),
        "documents_digest_after": hashlib.sha256(json.dumps(docs_after, sort_keys=True).encode()).hexdigest(),
        "source_changes": sorted(path for path in set(before.get("files", {})) | set(after.get("files", {})) if before.get("files", {}).get(path) != after.get("files", {}).get(path)),
        "postgres": postgres,
    })
    _write_json(attempt / "commands.json", commands)
    _write_proof_outputs(attempt, proof, manifest_before, commands)

    reports_ok = all(report["status"] == "PASS" for report in junit) and browser["status"] == "PASS" and browser_output_valid
    commands_ok = all(item.get("exit_code") == 0 for item in commands.values()) and collection_valid
    postgres_ok = postgres["status"] == "AVAILABLE"
    hard_failure = (
        not reports_ok or not commands_ok or not source_unchanged or not protected_unchanged
        or not static_unchanged or not docs_unchanged or not git_ok or package.get("status") == "FAIL"
    )
    blocked = proof["status"] != "PROVEN" or not postgres_ok or not package.get("origin_valid")
    final_status = "FAILED" if hard_failure else "BLOCKED" if blocked else "PASS"
    _write_json(attempt / "result.json", {
        "attempt_id": attempt.name,
        "status": final_status,
        "proof_status": proof["status"],
        "reports_valid": reports_ok,
        "commands_valid": commands_ok,
        "source_unchanged": bool(source_unchanged),
        "protected_unchanged": protected_unchanged,
        "generated_static_unchanged": static_unchanged,
        "final_documents_unchanged": docs_unchanged,
        "git_metadata_valid": git_ok,
        "postgres_required_and_available": postgres_ok,
        "package_origin_valid": package.get("origin_valid"),
        "junit": junit,
        "playwright": browser,
        "playwright_output_matches_report": browser_output_valid,
    })
    print(f"Gate 6 offline evidence: {final_status}; evidence at {attempt}")
    return 0 if final_status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
