from __future__ import annotations

import re

from fastapi.testclient import TestClient
import pytest

from shiftguard.api.main import create_app
from shiftguard.settings import Settings


def test_built_entry_asset_has_javascript_mime_type_and_product_content(tmp_path) -> None:
    app = create_app(Settings(SHIFTGUARD_DB_URL=f"sqlite:///{tmp_path / 'shiftguard.db'}"))

    with TestClient(app) as client:
        page = client.get("/")
        assert page.status_code == 200
        entry = re.search(r'<script[^>]+src="([^\"]+\.js)"', page.text)
        assert entry is not None, "built index must reference its generated JavaScript entry"
        asset_path = entry.group(1)
        assert asset_path.startswith("/assets/")
        response = client.get(asset_path)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/javascript")
    assert "SHIFTGUARD" in response.text
    assert "bank-stress" in response.text
    assert "plotly" in response.text.lower()


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
