from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from shiftguard.settings import Settings


_DATABASES = ["sqlite"]
if os.environ.get("SHIFTGUARD_TEST_POSTGRES_URL"):
    _DATABASES.append("postgresql")


@pytest.fixture(params=_DATABASES, ids=_DATABASES)
def ordinary_test_settings(request, tmp_path):
    if request.param == "sqlite":
        yield Settings(
            _env_file=None,
            db_url=f"sqlite:///{tmp_path / 'ordinary-runtime.sqlite'}",
        )
        return

    process_url = os.environ["SHIFTGUARD_TEST_POSTGRES_URL"]
    admin = create_engine(process_url, connect_args={"connect_timeout": 3})
    schema = "sg_ordinary_" + uuid4().hex
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    base_url = make_url(process_url)
    isolated_url = base_url.update_query_dict(
        {"options": f"-csearch_path={schema}"}
    ).render_as_string(hide_password=False)
    try:
        yield Settings(
            _env_file=None,
            db_url=isolated_url,
            environment="hosted",
        )
    finally:
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
