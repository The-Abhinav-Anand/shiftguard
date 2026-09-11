from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from shiftguard.migrations import upgrade_database
from shiftguard.settings import Settings, _deepest_mount_filesystem
from shiftguard.storage.db import configure_sqlite_connection, create_engine_for_settings


def test_relative_sqlite_url_resolves_from_the_repository_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)

    settings = Settings()

    assert settings.sqlite_path == tmp_path / "var" / "shiftguard.db"
    assert settings.sqlalchemy_url.database == "./var/shiftguard.db"


def test_default_database_directory_exists_before_migration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    settings = Settings()

    upgrade_database(settings)

    assert settings.sqlite_path.exists()


def test_unsupported_sqlite_is_rejected_before_migration_writes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    database_path = tmp_path / "blocked.db"
    settings = Settings(SHIFTGUARD_DB_URL=f"sqlite:///{database_path.as_posix()}")
    monkeypatch.setattr(
        "shiftguard.storage.db.validate_local_sqlite_runtime",
        lambda: (_ for _ in ()).throw(RuntimeError("unsupported SQLite version for WAL")),
    )

    with pytest.raises(RuntimeError, match="unsupported SQLite version"):
        upgrade_database(settings)

    assert not database_path.exists()


def test_direct_alembic_uses_validated_environment_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    database_path = tmp_path / "direct-alembic.db"
    monkeypatch.setenv("SHIFTGUARD_DB_URL", f"sqlite:///{database_path.as_posix()}")
    monkeypatch.setenv("SHIFTGUARD_ENVIRONMENT", "local")
    config = Config(str(Path(__file__).parents[2] / "alembic.ini"))

    command.upgrade(config, "head")

    settings = Settings(SHIFTGUARD_DB_URL=f"sqlite:///{database_path.as_posix()}")
    engine = create_engine_for_settings(settings)
    try:
        assert "alembic_version" in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_postgresql_url_is_normalized_to_psycopg_without_connecting() -> None:
    settings = Settings(
        SHIFTGUARD_ENVIRONMENT="hosted",
        SHIFTGUARD_DB_URL="postgresql://shiftguard:pa%40ss@db.example/shiftguard",
    )

    assert settings.sqlalchemy_url.drivername == "postgresql+psycopg"
    assert settings.sqlalchemy_url.password == "pa@ss"
    engine = create_engine_for_settings(settings)
    try:
        assert engine.url.drivername == "postgresql+psycopg"
    finally:
        engine.dispose()


def test_unknown_postgresql_driver_is_rejected() -> None:
    with pytest.raises(ValueError, match="PostgreSQL driver"):
        Settings(
            SHIFTGUARD_ENVIRONMENT="hosted",
            SHIFTGUARD_DB_URL="postgresql+asyncpg://shiftguard:secret@db.example/shiftguard",
        )


def test_deepest_mount_matching_does_not_accept_prefix_siblings() -> None:
    filesystem = _deepest_mount_filesystem(
        Path("C:/mnt/share/cache-backup/shiftguard.db"),
        [
            (Path("C:/mnt/share"), "nfs"),
            (Path("C:/mnt/share/cache"), "ext4"),
        ],
    )

    assert filesystem == "nfs"


def test_sqlite_uri_memory_options_are_rejected() -> None:
    with pytest.raises(ValueError, match="SQLite URI options"):
        Settings(SHIFTGUARD_DB_URL="sqlite:///file:gate0_review?mode=memory&cache=shared&uri=true")


def test_sqlite_wal_refusal_is_reported() -> None:
    import sqlite3

    connection = sqlite3.connect(":memory:")
    try:
        with pytest.raises(RuntimeError, match="WAL could not be enabled"):
            configure_sqlite_connection(connection)
    finally:
        connection.close()
