from __future__ import annotations

from sqlalchemy import inspect

from shiftguard.migrations import upgrade_database
from shiftguard.settings import Settings
from shiftguard.storage.db import create_engine_for_settings


def test_upgrade_creates_schema_version_table(tmp_path) -> None:
    settings = Settings(SHIFTGUARD_DB_URL=f"sqlite:///{tmp_path / 'shiftguard.db'}")

    upgrade_database(settings)

    engine = create_engine_for_settings(settings)
    try:
        assert "alembic_version" in inspect(engine).get_table_names()
    finally:
        engine.dispose()
