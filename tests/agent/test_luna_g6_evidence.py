"""Negative hygiene tests for report-derived Gate 6 evidence."""

from __future__ import annotations

import json
import ast
from pathlib import Path
import re

from scripts import execute_gate6_offline_suite as evidence


def test_luna_g6_evidence_postgres_helper_notice_keeps_service_available(monkeypatch):
    from types import SimpleNamespace
    fixture_url = "postgresql+psycopg://fixture:fixture@127.0.0.1:15432/test"
    stdout = "Existing PostgreSQL16 test connection verified; URL configured for this process only.\n" + fixture_url
    monkeypatch.setattr(evidence.subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(returncode=0, stdout=stdout, stderr=""))
    env = {}
    status = evidence._postgres_environment(env)
    assert status == {"status": "AVAILABLE", "helper_exit": 0, "url_redacted": True}
    assert env["SHIFTGUARD_TEST_POSTGRES_URL"] == fixture_url


def test_luna_g6_evidence_postgres_helper_rejects_ambiguous_or_failed_output(monkeypatch):
    from types import SimpleNamespace
    fixture_url = "postgresql+psycopg://fixture:fixture@127.0.0.1:15432/test"
    for exit_code, stdout in ((0, fixture_url + "\n" + fixture_url), (1, fixture_url), (0, "no endpoint")):
        monkeypatch.setattr(evidence.subprocess, "run", lambda *args, **kwargs:
                            SimpleNamespace(returncode=exit_code, stdout=stdout, stderr=""))
        env = {}
        assert evidence._postgres_environment(env)["status"] == "BLOCKED"
        assert "SHIFTGUARD_TEST_POSTGRES_URL" not in env


def test_luna_g6_evidence_redaction_preserves_distinct_collection_parameter_identity():
    raw = "\n".join([
        "tests/unit/test_urls.py::test_url[postgresql://fixture:a@localhost/db]",
        "tests/unit/test_urls.py::test_url[postgresql://fixture:b@localhost/db]",
        "2 tests collected",
    ])
    safe = evidence._safe_output(raw, {})
    assert "fixture:" not in safe and "localhost" not in safe
    valid, nodes, count = evidence.collection_output_valid(safe, 0)
    assert valid and count == 2 and len(set(nodes)) == 2
    assert all(node.endswith("]]") for node in nodes)
    duplicate = raw.splitlines()[0] + "\n" + raw.splitlines()[0] + "\n2 tests collected"
    assert not evidence.collection_output_valid(evidence._safe_output(duplicate, {}), 0)[0]


def _junit(path, cases, *, declared_tests=None, root_tests=None):
    test_count = len(cases) if declared_tests is None else declared_tests
    root_count = test_count if root_tests is None else root_tests
    failures = sum("<failure" in marker for _classname, _name, marker in cases)
    errors = sum("<error" in marker for _classname, _name, marker in cases)
    skipped = sum("<skipped" in marker for _classname, _name, marker in cases)
    body = "".join(
        f'<testcase classname="{classname}" name="{name}">{marker}</testcase>'
        for classname, name, marker in cases
    )
    path.write_text(
        f'<testsuites tests="{root_count}" failures="{failures}" errors="{errors}" skipped="{skipped}">'
        f'<testsuite tests="{test_count}" failures="{failures}" errors="{errors}" skipped="{skipped}">{body}</testsuite>'
        "</testsuites>",
        encoding="utf-8",
    )
    return evidence.parse_junit_xml(path)


def _playwright(nodes, *, stats=None, metadata=None):
    counts = {
        "expected": sum(node["outcome"] == "passed" for node in nodes),
        "unexpected": sum(node["outcome"] in ("failed", "flaky") for node in nodes),
        "skipped": sum(node["outcome"] == "skipped" for node in nodes),
        "flaky": sum(node["outcome"] == "flaky" for node in nodes),
    }
    return {
        "config": {"metadata": metadata or {
            "providerKind": "scripted-test-harness",
            "evidenceMode": "scripted",
            "liveProviderCalls": False,
        }},
        "suites": [{"title": "root", "suites": [{
        "title": "nested",
        "specs": [{"title": node["title"], "tests": [{
            "status": {"passed": "expected", "failed": "unexpected", "flaky": "flaky", "skipped": "skipped"}[node["outcome"]],
            "results": [{"status": "passed" if node["outcome"] == "passed" else node["outcome"]}],
        }]} for node in nodes],
        "suites": [],
    }]}], "stats": stats or counts,
    }


def test_luna_g6_evidence_p06_positive_real_nodes(tmp_path):
    path = tmp_path / "actual.xml"
    report = _junit(path, [
        ("tests.agent.test_luna_g6_grounding_backends", "test_luna_g6_all_eight_readers_fail_closed_before_storage_lookup[sqlite]", ""),
        ("tests.agent.test_luna_g6_grounding_backends", "test_luna_g6_all_eight_readers_fail_closed_before_storage_lookup[postgres]", ""),
        ("tests.agent.test_luna_g6_grounding_backends", "test_luna_g6_authorized_reader_returns_strict_projection_without_private_metadata[sqlite]", ""),
        ("tests.agent.test_luna_g6_grounding_backends", "test_luna_g6_authorized_reader_returns_strict_projection_without_private_metadata[postgres]", ""),
    ])
    proof = evidence.derive_proof_map([report], {"nodes": []}, {"G6-S09": evidence.PROOF_CASES["G6-S09"]})
    assert report["tests"] == 4 and report["status"] == "PASS"
    assert proof["findings"]["G6-S09"]["status"] == "PROVEN"


def _write_playwright(path, report):
    path.write_text(json.dumps(report), encoding="utf-8")
    return path


def test_luna_g6_evidence_p06_junit_skips_and_missing_nodes_rejected(tmp_path):
    skipped = _junit(tmp_path / "skipped.xml", [
        ("tests.agent.test_db", "test_backend[sqlite]", "<skipped/>"),
        ("tests.agent.test_db", "test_backend[postgresql]", "<skipped/>"),
    ])
    assert skipped["status"] == "FAIL"
    assert evidence.parse_junit_xml(tmp_path / "missing.xml")["status"] == "FAIL"


def test_luna_g6_evidence_p06_junit_count_mismatch_rejected(tmp_path):
    report = _junit(tmp_path / "invented-count.xml", [
        ("tests.agent.test_case", "test_actual", ""),
    ], declared_tests=34, root_tests=34)
    assert report["status"] == "FAIL"
    assert report["counter_errors"]


def test_luna_g6_evidence_p06_playwright_recursive_and_skip_rejected(tmp_path):
    actual_p01_titles = [case["title"] for case in evidence.PROOF_CASES["G6-P01"]["browser_cases"]]
    valid = _write_playwright(tmp_path / "valid.json", _playwright([
        {"title": title, "outcome": "passed"} for title in actual_p01_titles
    ]))
    parsed = evidence.parse_playwright_json(valid)
    assert parsed["status"] == "PASS"
    assert len(parsed["nodes"]) == len(actual_p01_titles)
    bad = _write_playwright(tmp_path / "skipped.json", _playwright([
        {"title": title, "outcome": "passed" if index == 0 else "skipped"}
        for index, title in enumerate(actual_p01_titles)
    ]))
    parsed_bad = evidence.parse_playwright_json(bad)
    assert parsed_bad["status"] == "FAIL"
    fake_stats = _playwright([{ "title": "fake positive", "outcome": "passed" }], stats={
        "expected": 34, "unexpected": 0, "skipped": 0, "flaky": 0,
    })
    fake = _write_playwright(tmp_path / "fake-stats.json", fake_stats)
    assert evidence.parse_playwright_json(fake)["status"] == "FAIL"
    assert evidence.parse_playwright_json(tmp_path / "missing.json")["status"] == "FAIL"
    assert evidence.playwright_output_matches(f"{len(actual_p01_titles)} passed (1.2s)", parsed)
    assert not evidence.playwright_output_matches("34 passed (1.2s)", parsed)
    wrong_harness = _write_playwright(tmp_path / "wrong-harness.json", _playwright([
        {"title": title, "outcome": "passed"} for title in actual_p01_titles
    ], metadata={"providerKind": "hosted", "evidenceMode": "live", "liveProviderCalls": True}))
    assert evidence.parse_playwright_json(wrong_harness)["status"] == "FAIL"


def test_luna_g6_evidence_p06_wrong_backend_and_missing_finding_rejected(tmp_path):
    report = _junit(tmp_path / "sqlite-only.xml", [
        ("tests.agent.test_luna_g6_grounding_backends", "test_luna_g6_all_eight_readers_fail_closed_before_storage_lookup[sqlite]", ""),
        ("tests.agent.test_luna_g6_grounding_backends", "test_luna_g6_authorized_reader_returns_strict_projection_without_private_metadata[sqlite]", ""),
    ])
    proof = evidence.derive_proof_map([report], {"nodes": []}, {
        "G6-S09": evidence.PROOF_CASES["G6-S09"],
        "G6-S01": evidence.PROOF_CASES["G6-S01"],
    })
    assert proof["findings"]["G6-S09"]["status"] == "BLOCKED"
    assert proof["findings"]["G6-S09"]["missing_backends"] == ["postgresql"]
    assert "test_luna_g6_protocol_recovers_the_saved_decision" in proof["findings"]["G6-S01"]["missing_cases"]
    assert proof["status"] == "BLOCKED"

    skewed = _junit(tmp_path / "skewed-backend-coverage.xml", [
        ("tests.agent.test_luna_g6_grounding_backends", "test_luna_g6_authorized_reader_returns_strict_projection_without_private_metadata[sqlite]", ""),
        ("tests.agent.test_luna_g6_grounding_backends", "test_luna_g6_all_eight_readers_fail_closed_before_storage_lookup[postgres]", ""),
        ("tests.agent.test_luna_g6_grounding_backends", "test_luna_g6_authorized_reader_returns_strict_projection_without_private_metadata_decoy[postgres]", ""),
    ])
    skewed_proof = evidence.derive_proof_map([skewed], {"nodes": []}, {"G6-S09": evidence.PROOF_CASES["G6-S09"]})
    finding = skewed_proof["findings"]["G6-S09"]
    assert finding["status"] == "BLOCKED"
    assert "test_luna_g6_authorized_reader_returns_strict_projection_without_private_metadata[postgresql]" in finding["missing_backend_cases"]
    assert "test_luna_g6_all_eight_readers_fail_closed_before_storage_lookup[sqlite]" in finding["missing_backend_cases"]


def test_luna_g6_evidence_p06_source_drift_and_package_origin_rejected(tmp_path):
    before = {"available": True, "files": {"shiftguard/settings.py": "before"}}
    same = {"available": True, "files": {"shiftguard/settings.py": "before"}}
    changed = {"available": True, "files": {"shiftguard/settings.py": "after"}}
    assert evidence.source_snapshots_match(before, same)
    assert not evidence.source_snapshots_match(before, changed)
    assert not evidence.source_snapshots_match(before, {"available": False, "files": before["files"]})

    extraction = tmp_path / "wheel"
    extraction.mkdir()
    assert evidence.package_origins_valid({"shiftguard": str(extraction / "shiftguard" / "__init__.py")}, extraction)
    assert not evidence.package_origins_valid({"shiftguard": str(tmp_path / "checkout" / "shiftguard" / "__init__.py")}, extraction)
    assert not evidence.package_origins_valid({}, extraction)


def test_luna_g6_evidence_p06_collection_nodes_match_declared_count():
    valid, nodes, count = evidence.collection_output_valid(
        "tests/agent/test_x.py::test_one\ntests/agent/test_x.py::test_two\n2 tests collected in 0.01s\n", 0,
    )
    assert valid and count == 2 and len(nodes) == 2
    forged, _nodes, _count = evidence.collection_output_valid("34 tests collected\n", 0)
    assert not forged
    failed_exit, _nodes, _count = evidence.collection_output_valid(
        "tests/agent/test_x.py::test_one\n1 test collected\n", 1,
    )
    assert not failed_exit


def test_luna_g6_evidence_p06_failed_canary_node_rejected(tmp_path):
    report_path = tmp_path / "failed-canary.xml"
    report_path.write_text(
        '<testsuites tests="1" failures="1" errors="0" skipped="0">'
        '<testsuite tests="1" failures="1" errors="0" skipped="0">'
        '<testcase classname="tests.agent.test_luna_g6_preflight" name="test_luna_g6_preflight_p03_exact_ping_required">'
        '<failure message="PONG did not match">assert False</failure>'
        '</testcase></testsuite></testsuites>',
        encoding="utf-8",
    )
    report = evidence.parse_junit_xml(report_path)
    proof = evidence.derive_proof_map([report], {"nodes": []}, {
        "G6-P03": {"cases": [{"node": "test_luna_g6_preflight_p03_exact_ping_required", "role": "negative"}]},
    })
    assert report["status"] == "FAIL"
    assert proof["findings"]["G6-P03"]["status"] == "FAILED"


def test_luna_g6_evidence_p06_actual_names_map_and_invented_aliases_stay_blocked(tmp_path):
    required_titles = [case["title"] for case in evidence.PROOF_CASES["G6-P01"]["browser_cases"]]
    actual = _junit(tmp_path / "real-names.xml", [
        ("tests.agent.test_luna_g6_grounding_backends", "test_luna_g6_all_eight_readers_fail_closed_before_storage_lookup[sqlite]", ""),
        ("tests.agent.test_luna_g6_grounding_backends", "test_luna_g6_all_eight_readers_fail_closed_before_storage_lookup[postgres]", ""),
        ("tests.agent.test_luna_g6_grounding_backends", "test_luna_g6_authorized_reader_returns_strict_projection_without_private_metadata[sqlite]", ""),
        ("tests.agent.test_luna_g6_grounding_backends", "test_luna_g6_authorized_reader_returns_strict_projection_without_private_metadata[postgres]", ""),
    ])
    browser = {"nodes": [{"title": title, "outcome": "passed"} for title in required_titles]}
    good = evidence.derive_proof_map([actual], browser, {
        "G6-S09": evidence.PROOF_CASES["G6-S09"],
        "G6-P01": evidence.PROOF_CASES["G6-P01"],
    })
    assert good["findings"]["G6-S09"]["status"] == "PROVEN"
    assert good["findings"]["G6-P01"]["status"] == "PROVEN"

    decoys = _junit(tmp_path / "decoy-names.xml", [
        ("tests.agent.test_luna_g6_grounding_backends", "test_luna_g6_all_eight_readers_fail_closed_before_storage_lookup_alias[sqlite]", ""),
    ])
    decoy_browser = {"nodes": [{"title": "reload exposes original intent after retry", "outcome": "passed"}]}
    blocked = evidence.derive_proof_map([decoys], decoy_browser, {
        "G6-S09": evidence.PROOF_CASES["G6-S09"],
        "G6-P01": evidence.PROOF_CASES["G6-P01"],
    })
    assert blocked["findings"]["G6-S09"]["status"] == "BLOCKED"
    assert "test_luna_g6_all_eight_readers_fail_closed_before_storage_lookup" in blocked["findings"]["G6-S09"]["missing_cases"]
    assert any("postgresql" in item for item in blocked["findings"]["G6-S09"]["missing_obligations"])
    assert blocked["findings"]["G6-P01"]["status"] == "BLOCKED"
    assert any("actual title" in item for item in blocked["findings"]["G6-P01"]["missing_obligations"])
    assert blocked["status"] == "BLOCKED"


def test_luna_g6_evidence_p06_p01_p02_titles_match_current_browser_spec():
    spec = Path(evidence.REPO_ROOT / "tests/e2e/test_agent_identity_luna3.spec.ts")
    actual_titles = set(re.findall(r'test\("([^"]+)"', spec.read_text(encoding="utf-8")))
    expected = {
        "G6-P01": {
            "[simulated] transport loss after real acceptance reloads the original intent and retries the same API identity",
            "actual WAITING request is rehydrated on reload with its job and server continuation identity",
            "Clear suppresses a delayed response after the real queue accepted the original POST",
            "agent intent storage failure is visible and prevents an unsaved POST",
        },
        "G6-P02": {
            "[simulated] actual accepted work remains bound to its expired session until an explicit reconnect",
            "[simulated] capability rejection Clear does not replace the expired authority",
            "[simulated] terminal API response renders structured and legacy tool errors safely",
        },
    }
    for finding, titles in expected.items():
        mapped = {case["title"] for case in evidence.PROOF_CASES[finding]["browser_cases"]}
        assert mapped == titles
        assert mapped <= actual_titles
    assert not any("[simulated transport loss after real acceptance]" in title for title in actual_titles)


def test_luna_g6_evidence_p06_backend_requirements_follow_database_obligations(tmp_path):
    provider_cases = evidence.PROOF_CASES["G6-P04"]["cases"]
    assert "backends" not in evidence.PROOF_CASES["G6-P04"]
    assert all("backends" not in case for case in provider_cases)
    provider_report = _junit(tmp_path / "provider-unparameterized.xml", [
        ("tests.agent.test_luna_g6_provider", case["node"], "")
        for case in provider_cases
    ])
    provider_proof = evidence.derive_proof_map([provider_report], {"nodes": []}, {
        "G6-P04": evidence.PROOF_CASES["G6-P04"],
    })
    assert provider_proof["findings"]["G6-P04"]["status"] == "PROVEN"
    assert provider_proof["findings"]["G6-P04"]["required_backends"] == []

    migration_cases = evidence.PROOF_CASES["G6-P05"]["cases"]
    package_case = next(case for case in migration_cases if case["node"] == "test_migration_resources_exist_in_package")
    assert "backends" not in package_case
    migration_nodes = []
    for case in migration_cases:
        if case.get("backends"):
            migration_nodes.extend(
                ("tests.agent.test_luna_g6_protocol", f'{case["node"]}[{backend}]', "")
                for backend in case["backends"]
            )
        else:
            migration_nodes.append(("tests.agent.test_migrations", case["node"], ""))
    migration_report = _junit(tmp_path / "migration-backends.xml", migration_nodes)
    migration_proof = evidence.derive_proof_map([migration_report], {"nodes": []}, {
        "G6-P05": evidence.PROOF_CASES["G6-P05"],
    })["findings"]["G6-P05"]
    assert migration_proof["status"] == "PROVEN"
    assert migration_proof["required_backends"] == ["postgresql", "sqlite"]
    assert migration_proof["observed_backends"] == ["postgresql", "sqlite"]

    sqlite_only = _junit(tmp_path / "migration-sqlite-only.xml", [
        (classname, name, "")
        for classname, name, _marker in migration_nodes
        if "[postgresql]" not in name
    ])
    blocked = evidence.derive_proof_map([sqlite_only], {"nodes": []}, {
        "G6-P05": evidence.PROOF_CASES["G6-P05"],
    })["findings"]["G6-P05"]
    assert blocked["status"] == "BLOCKED"
    assert blocked["missing_backends"] == ["postgresql"]


def test_luna_g6_evidence_p06_compound_backend_ids_are_bounded(tmp_path):
    assert evidence._backend_for_node(
        "tests.agent.test_luna_g6_protocol::test_luna_g6_protocol_recovers_the_saved_decision[postgresql-before_dispatch]"
    ) == "postgresql"
    assert evidence._backend_for_node(
        "tests.agent.test_luna_g6_protocol::test_luna_g6_protocol_terminal_job_error_survives_resume[postgresql-cancelled]"
    ) == "postgresql"
    assert evidence._backend_for_node("tests.agent.test_protocol::test_case[sqlite-after_admission]") == "sqlite"
    assert evidence._backend_for_node("tests.agent.test_protocol::test_case[not-postgres]") is None
    assert evidence._backend_for_node("tests.agent.test_protocol::test_case[not-postgresql]") is None
    assert evidence._backend_for_node("tests.agent.test_protocol::test_case[postgresqlish]") is None

    requirement = {"cases": [
        {"node": "test_luna_g6_protocol_recovers_the_saved_decision", "role": "positive", "backends": ["sqlite", "postgresql"]},
        {"node": "test_luna_g6_protocol_terminal_job_error_survives_resume", "role": "negative", "backends": ["sqlite", "postgresql"]},
    ]}
    valid = _junit(tmp_path / "compound-backends.xml", [
        ("tests.agent.test_luna_g6_protocol", "test_luna_g6_protocol_recovers_the_saved_decision[sqlite-before_dispatch]", ""),
        ("tests.agent.test_luna_g6_protocol", "test_luna_g6_protocol_recovers_the_saved_decision[postgresql-before_dispatch]", ""),
        ("tests.agent.test_luna_g6_protocol", "test_luna_g6_protocol_terminal_job_error_survives_resume[sqlite-cancelled]", ""),
        ("tests.agent.test_luna_g6_protocol", "test_luna_g6_protocol_terminal_job_error_survives_resume[postgresql-cancelled]", ""),
    ])
    proof = evidence.derive_proof_map([valid], {"nodes": []}, {"G6-S01": requirement})
    assert proof["findings"]["G6-S01"]["status"] == "PROVEN"

    decoys = _junit(tmp_path / "lookalike-backends.xml", [
        ("tests.agent.test_protocol", "test_luna_g6_protocol_recovers_the_saved_decision[not-postgresql]", ""),
        ("tests.agent.test_protocol", "test_luna_g6_protocol_terminal_job_error_survives_resume[postgresqlish]", ""),
    ])
    blocked = evidence.derive_proof_map([decoys], {"nodes": []}, {"G6-S01": requirement})["findings"]["G6-S01"]
    assert blocked["status"] == "BLOCKED"
    assert blocked["missing_backends"] == ["postgresql", "sqlite"]
    assert len(blocked["missing_backend_cases"]) == 4


def test_luna_g6_evidence_p06_registered_nodes_are_declared_permanent_tests():
    repo_root = Path(evidence.__file__).resolve().parent.parent
    declared = set()
    for source in (repo_root / "tests").rglob("test_*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        declared.update(
            node.name for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
        )
    registered = {
        case["node"]
        for requirement in evidence.PROOF_CASES.values()
        for case in requirement.get("cases", [])
    }
    assert registered
    assert registered <= declared
    assert "test_luna_g6_all_eight_readers_fail_closed_before_storage_lookup" in registered
    assert "test_luna_g6_valid_evidence_does_not_authorize_unchecked_provider_prose" in registered
