from __future__ import annotations

import sqlite3

import pytest
from pydantic import ValidationError

from shiftguard.settings import Settings, assert_supported_sqlite_version


def test_local_sqlite_url_is_accepted(tmp_path) -> None:
    settings = Settings(SHIFTGUARD_DB_URL=f"sqlite:///{tmp_path / 'shiftguard.db'}")

    assert settings.database_backend == "sqlite"
    assert settings.sqlite_path == tmp_path / "shiftguard.db"


@pytest.mark.parametrize(
    "url",
    [
        "sqlite:////server/share/shiftguard.db",
        "sqlite:///\\\\server\\share\\shiftguard.db",
        "sqlite://remote-host/shiftguard.db",
    ],
)
def test_sqlite_network_locations_are_rejected(url: str) -> None:
    with pytest.raises(ValidationError, match="local filesystem"):
        Settings(SHIFTGUARD_DB_URL=url)


def test_only_sqlite_and_postgresql_are_supported() -> None:
    with pytest.raises(ValidationError, match="SQLite or PostgreSQL"):
        Settings(SHIFTGUARD_DB_URL="mysql://localhost/shiftguard")


@pytest.mark.parametrize("version", [(3, 42, 0), (3, 51, 1)])
def test_sqlite_wal_bug_versions_are_rejected(version: tuple[int, int, int]) -> None:
    with pytest.raises(RuntimeError, match="unsupported SQLite version"):
        assert_supported_sqlite_version(version)


def test_first_supported_sqlite_version_is_accepted() -> None:
    assert_supported_sqlite_version((3, 51, 3))


def test_current_runtime_sqlite_version_is_checked() -> None:
    assert_supported_sqlite_version(sqlite3.sqlite_version_info)
