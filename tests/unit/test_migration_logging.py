"""In-process migrations must not silence loggers that already exist (server and app logs)."""

from __future__ import annotations

import logging

from shiftguard.migrations import upgrade_database
from shiftguard.settings import Settings


def test_upgrade_keeps_existing_loggers_enabled(tmp_path):
    names = ("uvicorn.error", "uvicorn.access", "shiftguard.agent.provider", "shiftguard.jobs.worker")
    loggers = [logging.getLogger(name) for name in names]
    for logger in loggers:
        logger.disabled = False
    settings = Settings(_env_file=None, db_url=f"sqlite:///{(tmp_path / 'logging.sqlite').as_posix()}")

    upgrade_database(settings)

    assert {logger.name: logger.disabled for logger in loggers} == {name: False for name in names}
