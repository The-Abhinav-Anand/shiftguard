from __future__ import annotations

from sqlalchemy import text

from shiftguard.settings import Settings
from shiftguard.storage.db import create_engine_for_settings


def test_sqlite_engine_enables_wal(tmp_path) -> None:
    settings = Settings(SHIFTGUARD_DB_URL=f"sqlite:///{tmp_path / 'shiftguard.db'}")
    engine = create_engine_for_settings(settings)
    try:
        with engine.connect() as connection:
            journal_mode = connection.execute(text("PRAGMA journal_mode")).scalar_one()
    finally:
        engine.dispose()

    assert journal_mode.lower() == "wal"


def test_database_connection_runs_sql(tmp_path) -> None:
    settings = Settings(SHIFTGUARD_DB_URL=f"sqlite:///{tmp_path / 'shiftguard.db'}")
    engine = create_engine_for_settings(settings)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        engine.dispose()
