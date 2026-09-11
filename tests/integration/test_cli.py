from __future__ import annotations

from typer.testing import CliRunner

from shiftguard.cli import app


def test_cli_reports_bootstrap_status(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'shiftguard.db'}"
    result = CliRunner().invoke(app, ["--db-url", database_url, "status"])

    assert result.exit_code == 0
    assert "Gate 0 bootstrap ready" in result.stdout
