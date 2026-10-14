from __future__ import annotations

import os
from pathlib import Path
import pytest
from sqlalchemy import text

from shiftguard.migrations import ALEMBIC_INI_PATH, ALEMBIC_SCRIPT_DIR, upgrade_database
from shiftguard.settings import Settings
from shiftguard.storage.db import create_engine_for_settings


def test_migration_resources_exist_in_package():
    """Verify migration resources are packaged alongside shiftguard."""
    assert ALEMBIC_INI_PATH.is_file(), f"alembic.ini missing from package: {ALEMBIC_INI_PATH}"
    assert ALEMBIC_SCRIPT_DIR.is_dir(), f"alembic script dir missing from package: {ALEMBIC_SCRIPT_DIR}"
    env_py = ALEMBIC_SCRIPT_DIR / "env.py"
    assert env_py.is_file(), f"env.py missing from package: {env_py}"
    versions_dir = ALEMBIC_SCRIPT_DIR / "versions"
    assert versions_dir.is_dir(), f"versions dir missing from package: {versions_dir}"

    expected_revisions = {
        "0001_gate0.py",
        "0002_gate1_experiments.py",
        "0003_gate1_execution_audit.py",
        "0004_publication_records.py",
        "0005_gate4_jobs_and_continuation.py",
        "0006_gate4_hardening.py",
        "0007_gate4_r4_hardening.py",
        "0008_gate4_attempt_binding.py",
    }
    actual_revisions = {p.name for p in versions_dir.glob("*.py") if not p.name.startswith("__")}
    assert expected_revisions.issubset(actual_revisions)


def test_upgrade_database_from_isolated_working_directory(tmp_path, monkeypatch):
    """A09 regression: upgrade_database must succeed when executed from an empty directory outside the repo."""
    empty_dir = tmp_path / "completely_empty_workdir"
    empty_dir.mkdir()
    monkeypatch.chdir(empty_dir)

    db_file = empty_dir / "isolated.db"
    settings = Settings(SHIFTGUARD_DB_URL=f"sqlite:///{db_file}")

    upgrade_database(settings)

    engine = create_engine_for_settings(settings)
    try:
        with engine.connect() as conn:
            rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            assert rev == "0012_ordinary_chat_and_budget"

            table_rows = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            ).fetchall()
            tables = {r[0] for r in table_rows}
            assert "application_metadata" in tables
            assert "experiments" in tables
            assert "experiment_executions" in tables
            assert "experiment_publications" in tables
            assert "jobs" in tables
            assert "job_events" in tables
            assert "agent_sessions" in tables
            assert "idempotency_records" in tables
            assert "continuation_receipts" in tables
            assert "shiftguard_chat_conversations" in tables
            assert "shiftguard_chat_messages" in tables
            assert "shiftguard_chat_receipts" in tables
            assert "ordinary_budget_daily" in tables
            assert "ordinary_budget_calls" in tables
    finally:
        engine.dispose()
