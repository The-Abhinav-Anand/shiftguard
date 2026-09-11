from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from shiftguard.settings import Settings
from shiftguard.storage.db import create_engine_for_settings


@pytest.mark.live
@pytest.mark.postgres
def test_postgresql_16_connection_when_explicitly_configured() -> None:
    url = os.getenv("SHIFTGUARD_TEST_POSTGRES_URL")
    if url is None:
        pytest.skip("set SHIFTGUARD_TEST_POSTGRES_URL to run PostgreSQL integration tests")
    settings = Settings(SHIFTGUARD_ENVIRONMENT="hosted", SHIFTGUARD_DB_URL=url)
    engine = create_engine_for_settings(settings)
    try:
        with engine.connect() as connection:
            assert "PostgreSQL 16" in connection.execute(text("SELECT version()")).scalar_one()
    finally:
        engine.dispose()
