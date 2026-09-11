from __future__ import annotations

from sqlalchemy import Engine, create_engine, event, text

from shiftguard.settings import Settings, validate_local_sqlite_runtime


def configure_sqlite_connection(dbapi_connection) -> None:
    cursor = dbapi_connection.cursor()
    try:
        journal_mode = cursor.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        if str(journal_mode).lower() != "wal":
            raise RuntimeError("SQLite WAL could not be enabled")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def create_engine_for_settings(settings: Settings) -> Engine:
    if settings.database_backend == "sqlite":
        validate_local_sqlite_runtime()
        settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(settings.sqlalchemy_url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def configure_sqlite_wal(dbapi_connection, _connection_record) -> None:
            configure_sqlite_connection(dbapi_connection)

        return engine
    return create_engine(settings.sqlalchemy_url, pool_pre_ping=True)


def check_database_connection(engine: Engine) -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
