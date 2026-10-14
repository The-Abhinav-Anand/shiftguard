"""Exclusive, database-scoped ownership of ordinary provider dispatch.

The ordinary ledger recovers open reservations by assuming their process died.
That is only true when one process owns dispatch for a database, so an app
acquires this owner before recovery or provider creation and holds it for its
whole lifespan. A second live owner is refused without touching the ledger.

PostgreSQL: a session advisory lock on a dedicated autocommit connection that
is never returned to the pool while owned. The 64-bit key is the first eight
bytes (big-endian, signed) of SHA-256 over ``_NAMESPACE``, the current database
and the effective schema, each separated by a NUL byte.

SQLite: an OS lock held on a sidecar file beside the canonical database path
(``msvcrt.locking`` on Windows, ``fcntl.flock`` elsewhere). The file existing
is not ownership, and a held sidecar is never unlinked to bypass contention.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import threading

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine


_NAMESPACE = b"shiftguard.ordinary-dispatch-owner.v1"
SQLITE_SIDECAR_SUFFIX = ".ordinary-owner.lock"


class OrdinaryOwnerUnavailable(RuntimeError):
    """Another process owns ordinary dispatch, or this process lost ownership."""


def postgres_owner_key(database: str, schema: str) -> int:
    digest = hashlib.sha256(
        _NAMESPACE + b"\0" + database.encode("utf-8") + b"\0" + schema.encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


def sqlite_owner_path(database: str) -> Path:
    path = Path(database).resolve()
    return path.with_name(path.name + SQLITE_SIDECAR_SUFFIX)


def _lock_file(fd: int) -> None:
    os.lseek(fd, 0, os.SEEK_SET)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_file(fd: int) -> None:
    os.lseek(fd, 0, os.SEEK_SET)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_UN)


class OrdinaryDispatchOwner:
    """Hold exclusive ordinary-dispatch ownership for one database."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self._guard = threading.Lock()
        self._held = False
        self._lost = False
        self._closed = False
        self._connection: Connection | None = None
        self._key: int | None = None
        self._fd: int | None = None
        self._path: Path | None = None

    @property
    def backend(self) -> str:
        return self.engine.dialect.name

    def acquire(self) -> None:
        with self._guard:
            if self._closed or self._lost:
                raise OrdinaryOwnerUnavailable("ordinary dispatch ownership cannot be reacquired")
            if self._held:
                return
            if self.backend == "postgresql":
                self._acquire_postgres()
            elif self.backend == "sqlite":
                self._acquire_sqlite()
            else:
                raise OrdinaryOwnerUnavailable(
                    f"ordinary dispatch ownership is unsupported for {self.backend}"
                )
            self._held = True

    def _acquire_postgres(self) -> None:
        connection = self.engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        try:
            database, schema = connection.execute(
                text("SELECT current_database(), current_schema()")
            ).one()
            if not schema:
                raise OrdinaryOwnerUnavailable("PostgreSQL effective schema is unavailable")
            key = postgres_owner_key(database, schema)
            acquired = connection.execute(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": key}
            ).scalar_one()
        except BaseException:
            connection.invalidate()
            connection.close()
            raise
        if not acquired:
            connection.invalidate()
            connection.close()
            raise OrdinaryOwnerUnavailable("another process owns ordinary dispatch for this database")
        self._connection = connection
        self._key = key

    def _acquire_sqlite(self) -> None:
        database = self.engine.url.database
        if not database or database == ":memory:" or self.engine.url.query.get("mode") == "memory":
            raise OrdinaryOwnerUnavailable(
                "in-memory SQLite cannot provide cross-process ordinary dispatch ownership"
            )
        path = sqlite_owner_path(database)
        fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o600)
        try:
            _lock_file(fd)
        except OSError:
            os.close(fd)
            raise OrdinaryOwnerUnavailable(
                "another process owns ordinary dispatch for this database"
            ) from None
        self._fd = fd
        self._path = path

    def assert_held(self) -> None:
        with self._guard:
            if not self._held or self._lost or self._closed:
                raise OrdinaryOwnerUnavailable("ordinary dispatch ownership is not held")
            try:
                held = (
                    self._postgres_still_held()
                    if self.backend == "postgresql"
                    else self._sqlite_still_held()
                )
            except Exception:
                held = False
            if not held:
                self._lost = True
                raise OrdinaryOwnerUnavailable("ordinary dispatch ownership was lost")

    def _postgres_still_held(self) -> bool:
        assert self._connection is not None and self._key is not None
        count = self._connection.execute(
            text(
                "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' "
                "AND pid = pg_backend_pid() AND granted AND objsubid = 1 "
                "AND classid::bigint = :high AND objid::bigint = :low"
            ),
            {"high": (self._key >> 32) & 0xFFFFFFFF, "low": self._key & 0xFFFFFFFF},
        ).scalar_one()
        return count == 1

    def _sqlite_still_held(self) -> bool:
        assert self._fd is not None and self._path is not None
        held = os.fstat(self._fd)
        current = os.stat(self._path)
        return (held.st_dev, held.st_ino) == (current.st_dev, current.st_ino)

    def close(self) -> None:
        with self._guard:
            if self._closed:
                return
            self._closed = True
            self._held = False
            if self._connection is not None:
                connection, self._connection = self._connection, None
                try:
                    connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": self._key})
                except Exception:
                    pass
                finally:
                    # Never hand a connection that held the session lock back to the pool.
                    connection.invalidate()
                    connection.close()
            if self._fd is not None:
                fd, self._fd = self._fd, None
                try:
                    _unlock_file(fd)
                except OSError:
                    pass
                finally:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
