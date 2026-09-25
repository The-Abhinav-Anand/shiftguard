from __future__ import annotations

import pytest

import verification.verify_gate2_reproduction as gate2
import verification.verify_gate3_reproduction as gate3


@pytest.mark.parametrize("verifier", [gate2, gate3])
@pytest.mark.parametrize(
    ("input_url", "expected_url"),
    [
        (
            "postgresql+psycopg://user:p%40ss%3Aword@localhost:15432/db"
            "?sslmode=require&options=-csearch_path%3Dtest_schema",
            "postgresql://user:p%40ss%3Aword@localhost:15432/db"
            "?sslmode=require&options=-csearch_path%3Dtest_schema",
        ),
        (
            "postgresql://user:p%40ss%3Aword@localhost:15432/db"
            "?sslmode=require&options=-csearch_path%3Dtest_schema",
            "postgresql://user:p%40ss%3Aword@localhost:15432/db"
            "?sslmode=require&options=-csearch_path%3Dtest_schema",
        ),
    ],
)
def test_verifier_passes_psycopg_compatible_url_unchanged_except_driver_prefix(
    verifier, monkeypatch, input_url, expected_url
):
    received = []
    sentinel = object()
    monkeypatch.setattr(verifier.psycopg, "connect", lambda url: received.append(url) or sentinel)

    connection = verifier.connect_postgres(input_url)

    assert connection is sentinel
    assert received == [expected_url]


@pytest.mark.parametrize("verifier", [gate2, gate3])
def test_verifier_does_not_rewrite_unsupported_driver_url(verifier, monkeypatch):
    input_url = "postgresql+asyncpg://user:secret@localhost/db"
    received = []

    def reject_url(url):
        received.append(url)
        raise ValueError("unsupported driver")

    monkeypatch.setattr(verifier.psycopg, "connect", reject_url)

    with pytest.raises(ValueError, match="unsupported driver"):
        verifier.connect_postgres(input_url)

    assert received == [input_url]
