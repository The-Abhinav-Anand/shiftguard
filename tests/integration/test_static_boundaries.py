from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from shiftguard.api.main import create_app
from shiftguard.settings import Settings


def test_static_asset_has_javascript_mime_type(tmp_path) -> None:
    app = create_app(Settings(SHIFTGUARD_DB_URL=f"sqlite:///{tmp_path / 'shiftguard.db'}"))

    with TestClient(app) as client:
        response = client.get("/assets/gate0.js")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/javascript")
    assert "SHIFTGUARD" in response.text


def test_missing_static_asset_is_a_404_not_spa(tmp_path) -> None:
    app = create_app(Settings(SHIFTGUARD_DB_URL=f"sqlite:///{tmp_path / 'shiftguard.db'}"))

    with TestClient(app) as client:
        response = client.get("/assets/missing.js")

    assert response.status_code == 404
    assert "SHIFTGUARD" not in response.text


@pytest.mark.parametrize("path", ["/api", "/api/", "/api/unknown"])
def test_api_prefix_never_falls_back_to_spa(path: str, tmp_path) -> None:
    app = create_app(Settings(SHIFTGUARD_DB_URL=f"sqlite:///{tmp_path / 'shiftguard.db'}"))

    with TestClient(app) as client:
        response = client.get(path)

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
