from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from shiftguard.settings import Settings
from shiftguard.storage.db import check_database_connection, create_engine_for_settings


def upgrade_database(settings: Settings) -> None:
    config = Config(str(Path(__file__).parent.parent / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).parent.parent / "alembic"))
    engine = create_engine_for_settings(settings)
    try:
        with engine.connect() as connection:
            config.attributes["connection"] = connection
            config.attributes["settings"] = settings
            command.upgrade(config, "head")
            check_database_connection(engine)
    finally:
        engine.dispose()
