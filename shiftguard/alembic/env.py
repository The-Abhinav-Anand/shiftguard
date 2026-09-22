from __future__ import annotations

from logging.config import fileConfig

from alembic import context

from shiftguard.settings import Settings
from shiftguard.storage.db import create_engine_for_settings


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def run_migrations_offline() -> None:
    settings = config.attributes.get("settings") or Settings()
    context.configure(
        url=settings.sqlalchemy_url.render_as_string(hide_password=False),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
        return

    engine = create_engine_for_settings(config.attributes.get("settings") or Settings())
    try:
        with engine.connect() as connection:
            context.configure(connection=connection)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
