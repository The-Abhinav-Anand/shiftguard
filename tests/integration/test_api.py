from __future__ import annotations

from fastapi.testclient import TestClient

from shiftguard.api.main import create_app
from shiftguard.settings import Settings


def test_health_reports_ready_after_migration(tmp_path) -> None:
    app = create_app(Settings(SHIFTGUARD_DB_URL=f"sqlite:///{tmp_path / 'shiftguard.db'}"))

    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ready"}


def test_unknown_api_path_is_json_404_not_spa(tmp_path) -> None:
    app = create_app(Settings(SHIFTGUARD_DB_URL=f"sqlite:///{tmp_path / 'shiftguard.db'}"))

    with TestClient(app) as client:
        response = client.get("/api/v1/not-implemented")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["detail"] == "Not Found"


def test_spa_fallback_does_not_shadow_api_routes(tmp_path) -> None:
    app = create_app(Settings(SHIFTGUARD_DB_URL=f"sqlite:///{tmp_path / 'shiftguard.db'}"))

    with TestClient(app) as client:
        response = client.get("/workspace")

    assert response.status_code == 200
    assert "SHIFTGUARD" in response.text
