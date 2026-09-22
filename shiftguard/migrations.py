from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from shiftguard.settings import Settings
from shiftguard.storage.db import check_database_connection, create_engine_for_settings

PACKAGE_ROOT = Path(__file__).resolve().parent
ALEMBIC_INI_PATH = PACKAGE_ROOT / "alembic.ini"
ALEMBIC_SCRIPT_DIR = PACKAGE_ROOT / "alembic"


def get_alembic_config(settings: Settings | None = None) -> Config:
    config = Config(str(ALEMBIC_INI_PATH))
    config.set_main_option("script_location", str(ALEMBIC_SCRIPT_DIR))
    if settings is not None:
        config.attributes["settings"] = settings
        raw_url = settings.sqlalchemy_url.render_as_string(hide_password=False)
        config.set_main_option("sqlalchemy.url", raw_url.replace("%", "%%"))
    return config


def upgrade_database(settings: Settings) -> None:
    config = get_alembic_config(settings)
    engine = create_engine_for_settings(settings)
    try:
        with engine.connect() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            check_database_connection(engine)
    finally:
        engine.dispose()

