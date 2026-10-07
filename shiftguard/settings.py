from __future__ import annotations

import ctypes
import os
import sqlite3
from pathlib import Path
import math
from typing import Iterable, Literal

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url


MINIMUM_SQLITE_WAL_VERSION = (3, 51, 3)


def assert_supported_sqlite_version(version: tuple[int, ...]) -> None:
    normalized = tuple(version[:3])
    if normalized < MINIMUM_SQLITE_WAL_VERSION:
        raise RuntimeError(f"unsupported SQLite version for WAL: {normalized!r}")


def _is_local_filesystem(path: Path) -> bool:
    if os.name != "nt":
        remote_filesystems = {"9p", "afs", "ceph", "cifs", "davfs", "fuse.sshfs", "glusterfs", "nfs", "nfs4", "smb3", "sshfs"}
        filesystem = _deepest_mount_filesystem(path, _mount_filesystems())
        return filesystem is not None and filesystem not in remote_filesystems

    resolved = path.resolve()
    root = f"{resolved.drive}\\" if resolved.drive else None
    if root is None:
        return False
    drive_remote = 4
    return ctypes.windll.kernel32.GetDriveTypeW(root) != drive_remote


def _mount_filesystems() -> list[tuple[Path, str]]:
    try:
        mounts = []
        for line in Path("/proc/mounts").read_text().splitlines():
            _source, mount_path, filesystem, *_options = line.split()
            mounts.append((Path(mount_path.replace("\\040", " ")).resolve(), filesystem))
        return mounts
    except (FileNotFoundError, ValueError):
        return []


def _deepest_mount_filesystem(path: Path, mounts: Iterable[tuple[Path, str]]) -> str | None:
    resolved = path.resolve()
    candidates = []
    for mount_path, filesystem in mounts:
        try:
            resolved.relative_to(mount_path.resolve())
        except ValueError:
            continue
        candidates.append((mount_path, filesystem))
    if not candidates:
        return None
    return max(candidates, key=lambda candidate: len(candidate[0].resolve().parts))[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", validate_assignment=True)

    db_url: str = Field(
        default="sqlite:///./var/shiftguard.db",
        validation_alias=AliasChoices("SHIFTGUARD_DB_URL", "db_url"),
    )
    environment: Literal["local", "hosted"] = Field(
        default="local",
        validation_alias=AliasChoices("SHIFTGUARD_ENVIRONMENT", "environment"),
    )
    artifact_root: Path = Field(
        default=Path("./var/artifacts"),
        validation_alias=AliasChoices("SHIFTGUARD_ARTIFACT_ROOT", "artifact_root"),
    )
    embedded_worker: bool = Field(
        default=False,
        validation_alias=AliasChoices("SHIFTGUARD_EMBEDDED_WORKER", "embedded_worker"),
    )
    worker_poll_interval: float = Field(
        default=0.5,
        validation_alias=AliasChoices("SHIFTGUARD_WORKER_POLL_INTERVAL", "worker_poll_interval"),
    )
    recovery_interval: float = Field(
        default=5.0,
        validation_alias=AliasChoices("SHIFTGUARD_RECOVERY_INTERVAL", "recovery_interval"),
    )
    nebius_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("NEBIUS_API_KEY", "nebius_api_key"),
        repr=False,
    )
    nebius_base_url: str = Field(
        default="https://api.tokenfactory.nebius.com/v1",
        validation_alias=AliasChoices("NEBIUS_BASE_URL", "nebius_base_url"),
    )
    nebius_model: str = Field(
        default="nvidia/Nemotron-3_5-Lightning",
        validation_alias=AliasChoices("NEBIUS_MODEL", "nebius_model"),
    )
    nebius_timeout: float = Field(
        default=25.0,
        gt=0.0,
        le=55.0,
        allow_inf_nan=False,
        validation_alias=AliasChoices("NEBIUS_TIMEOUT", "nebius_timeout"),
    )
    nebius_max_retries: int = Field(
        default=0,
        ge=0,
        le=0,
        validation_alias=AliasChoices("NEBIUS_MAX_RETRIES", "nebius_max_retries"),
    )
    nebius_max_output_tokens: int = Field(
        default=1024,
        ge=1,
        le=4096,
        validation_alias=AliasChoices("NEBIUS_MAX_OUTPUT_TOKENS", "nebius_max_output_tokens"),
    )
    nebius_enable_thinking: bool = Field(
        default=False,
        validation_alias=AliasChoices("NEBIUS_ENABLE_THINKING", "nebius_enable_thinking"),
    )
    agent_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("SHIFTGUARD_AGENT_ENABLED", "agent_enabled"),
    )
    agent_max_turns: int = Field(
        default=6,
        validation_alias=AliasChoices("SHIFTGUARD_AGENT_MAX_TURNS", "agent_max_turns"),
    )
    agent_max_calls: int = Field(
        default=8,
        validation_alias=AliasChoices("SHIFTGUARD_AGENT_MAX_CALLS", "agent_max_calls"),
    )
    agent_max_repairs: int = Field(
        default=1,
        validation_alias=AliasChoices("SHIFTGUARD_AGENT_MAX_REPAIRS", "agent_max_repairs"),
    )
    agent_timeout_seconds: float = Field(
        default=50.0,
        gt=0.0,
        le=55.0,
        allow_inf_nan=False,
        validation_alias=AliasChoices("SHIFTGUARD_AGENT_TIMEOUT_SECONDS", "agent_timeout_seconds"),
    )

    @field_validator("worker_poll_interval", "recovery_interval")
    @classmethod
    def validate_positive_finite_interval(cls, v: float) -> float:
        if not math.isfinite(v) or v <= 0.0:
            raise ValueError("interval must be a positive finite float")
        return v


    @model_validator(mode="after")
    def validate_database_profile(self) -> Settings:
        url = self.sqlalchemy_url
        if url.drivername == "sqlite":
            if self.environment != "local":
                raise ValueError("SQLite is only permitted in the local profile")
            if url.query:
                raise ValueError("SQLite URI options are not supported")
            if url.host is not None or url.database in {None, ":memory:"}:
                raise ValueError("SQLite WAL requires a local filesystem database")
            if self._is_windows_network_path(url.database):
                raise ValueError("SQLite WAL requires a local filesystem database")
            if not _is_local_filesystem(self.sqlite_path):
                raise ValueError("SQLite WAL requires a local filesystem database")
        elif url.drivername == "postgresql+psycopg":
            if self.environment != "hosted":
                raise ValueError("PostgreSQL requires the hosted profile")
        elif url.drivername.startswith("postgresql+"):
            raise ValueError("SHIFTGUARD_DB_URL must use the PostgreSQL driver psycopg")
        else:
            raise ValueError("SHIFTGUARD_DB_URL must use SQLite or PostgreSQL")
        return self

    @property
    def database_backend(self) -> Literal["sqlite", "postgresql"]:
        return "sqlite" if self.sqlalchemy_url.drivername == "sqlite" else "postgresql"

    @property
    def nebius_chat_template_kwargs(self) -> dict[str, bool]:
        return {"enable_thinking": self.nebius_enable_thinking}


    @property
    def sqlalchemy_url(self) -> URL:
        url = make_url(self.db_url)
        if url.drivername == "postgresql":
            return url.set(drivername="postgresql+psycopg")
        return url

    @property
    def sqlite_path(self) -> Path:
        database = self.sqlalchemy_url.database
        if database is None:
            raise RuntimeError("SQLite database path is required")
        return Path(database).resolve()

    @staticmethod
    def _is_windows_network_path(database: str | None) -> bool:
        if os.name != "nt" or database is None:
            return False
        normalized = database.replace("/", "\\")
        return normalized.startswith("\\\\") or (
            normalized.startswith("\\") and not Path(normalized).drive
        )


def validate_local_sqlite_runtime() -> None:
    assert_supported_sqlite_version(sqlite3.sqlite_version_info)
