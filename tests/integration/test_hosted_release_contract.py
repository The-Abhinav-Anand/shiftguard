"""Gate 10 release contract: readiness, deployment files and the offline acceptance probe."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import yaml
from starlette.testclient import TestClient

from shiftguard.api.main import create_app
from shiftguard.api.routes import health
from shiftguard.settings import Settings


APP_ROOT = Path(__file__).resolve().parents[2]
COMPOSE = APP_ROOT / "deploy" / "compose.judge.yaml"
CADDYFILE = APP_ROOT / "deploy" / "Caddyfile"
BOOTSTRAP = APP_ROOT / "deploy" / "bootstrap-vm.sh"


@pytest.fixture
def client(tmp_path, monkeypatch):
    health.reset_dataset_cache()
    settings = Settings(
        _env_file=None,
        db_url=f"sqlite:///{(tmp_path / 'release.sqlite').as_posix()}",
        artifact_root=str(tmp_path / "artifacts"),
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client
    health.reset_dataset_cache()


# --- readiness ----------------------------------------------------------------

def test_readiness_reports_database_migration_storage_and_verified_dataset(client):
    response = client.get("/health/ready")
    assert response.status_code == 200, response.text
    assert response.json() == {
        "status": "ready",
        "database": "connected",
        "migration": "head",
        "storage": "writable",
        "dataset": "verified",
    }


def test_readiness_fails_without_the_frozen_bank_dataset(client, monkeypatch, tmp_path):
    monkeypatch.setattr(health, "DATASET_CSV", tmp_path / "missing.csv")
    health.reset_dataset_cache()
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["error"]["details"] == {"reason": "dataset_unverified"}


def test_readiness_rejects_a_modified_dataset(client, monkeypatch, tmp_path):
    tampered = tmp_path / "bank.csv"
    tampered.write_bytes(health.DATASET_CSV.read_bytes() + b"\n")
    monkeypatch.setattr(health, "DATASET_CSV", tampered)
    health.reset_dataset_cache()
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["error"]["details"] == {"reason": "dataset_unverified"}
    assert str(tmp_path) not in response.text


def test_readiness_fails_when_the_schema_is_not_at_head(client, monkeypatch):
    monkeypatch.setattr(health, "_expected_head", lambda: "9999_not_applied")
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["error"]["details"] == {"reason": "migration_not_at_head"}


def test_readiness_never_echoes_database_errors(client, monkeypatch):
    def broken(_engine):
        raise RuntimeError("postgresql://user:secret@db/private")

    monkeypatch.setattr(health, "check_database_connection", broken)
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["error"]["details"] == {"reason": "database_unavailable"}
    assert "secret" not in response.text


def test_liveness_touches_no_dependency(client, monkeypatch):
    def broken(*_args, **_kwargs):
        raise AssertionError("liveness must not check dependencies")

    monkeypatch.setattr(health, "check_database_connection", broken)
    monkeypatch.setattr(health, "_dataset_verified", broken)
    assert client.get("/health/live").json() == {"status": "ok"}


# --- deployment files -----------------------------------------------------------

def _compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def test_compose_runs_one_api_one_worker_after_a_single_migration_step():
    services = _compose()["services"]
    assert set(services) == {"postgres", "migrate", "api", "worker", "caddy"}
    assert services["migrate"]["command"] == ["shiftguard", "status"]
    assert services["migrate"]["restart"] == "no"
    assert services["api"]["command"] == [
        "uvicorn", "shiftguard.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1",
    ]
    assert services["worker"]["command"] == [
        "shiftguard", "worker", "--poll-interval", "0.5", "--recovery-interval", "5",
    ]
    assert services["api"]["depends_on"]["migrate"]["condition"] == "service_completed_successfully"
    # The worker starts after the API is healthy, so no two processes upgrade at once.
    assert services["worker"]["depends_on"]["api"]["condition"] == "service_healthy"
    for name in ("api", "worker", "migrate"):
        assert services[name]["image"] == services["api"]["image"]
    assert "replicas" not in services["api"].get("deploy", {})


def test_compose_environment_is_hosted_offline_by_default_and_has_no_secrets():
    compose = _compose()
    services = compose["services"]
    for name in ("migrate", "api", "worker"):
        env = services[name]["environment"]
        assert env["SHIFTGUARD_ENVIRONMENT"] == "hosted"
        assert env["SHIFTGUARD_ARTIFACT_ROOT"] == "/app/var/artifacts"
        assert env["SHIFTGUARD_EMBEDDED_WORKER"] == "false"
        assert env["SHIFTGUARD_AGENT_ENABLED"] == "${SHIFTGUARD_AGENT_ENABLED:-false}"
        assert env["SHIFTGUARD_GENERAL_CHAT_ENABLED"] == "${SHIFTGUARD_GENERAL_CHAT_ENABLED:-false}"
        assert "SHIFTGUARD_DB_URL" not in env and "NEBIUS_API_KEY" not in env
        assert services[name]["env_file"] == ["judge.env"]
    assert services["postgres"]["env_file"] == ["postgres.env"]
    assert services["postgres"]["image"] == "postgres:16"
    text = COMPOSE.read_text(encoding="utf-8").lower()
    for marker in ("password=", "api_key=", "postgresql://", "postgres://"):
        assert marker not in text
    assert "ports" not in services["postgres"]
    assert services["api"]["ports"] == ["127.0.0.1:8000:8000"]


def test_compose_shares_durable_artifacts_and_mounts_data_read_only():
    compose = _compose()
    services = compose["services"]
    for name in ("api", "worker"):
        volumes = services[name]["volumes"]
        assert "artifacts:/app/var/artifacts" in volumes
        assert "${SHIFTGUARD_DATASET_DIR:-./datasets}:/app/var/datasets:ro" in volumes
    assert "pgdata:/var/lib/postgresql/data" in services["postgres"]["volumes"]
    assert set(compose["volumes"]) == {"artifacts", "pgdata", "caddy_data", "caddy_config"}


def test_caddy_terminates_https_for_the_configured_domain_in_front_of_the_single_api():
    services = _compose()["services"]
    caddy = services["caddy"]
    assert caddy["image"].startswith("caddy:2")
    assert caddy["environment"]["SHIFTGUARD_DOMAIN"] == "${SHIFTGUARD_DOMAIN:-localhost}"
    assert {"80:80", "443:443"} <= set(caddy["ports"])
    assert "./Caddyfile:/etc/caddy/Caddyfile:ro" in caddy["volumes"]
    # Certificates persist across restarts, so Let's Encrypt rate limits are never hit.
    assert "caddy_data:/data" in caddy["volumes"]
    assert "env_file" not in caddy  # the proxy never sees the database URL or the API key
    assert caddy["depends_on"]["api"]["condition"] == "service_started"
    # Only Caddy is public; the API stays on loopback and PostgreSQL is unpublished.
    for name, service in services.items():
        if name != "caddy":
            assert all(str(port).startswith("127.0.0.1:") for port in service.get("ports", [])), name

    caddyfile = CADDYFILE.read_text(encoding="utf-8")
    assert "{$SHIFTGUARD_DOMAIN:localhost} {" in caddyfile
    assert "reverse_proxy api:8000" in caddyfile
    assert "Strict-Transport-Security" in caddyfile


def test_bootstrap_script_installs_docker_builds_natively_and_never_echoes_secrets():
    raw = BOOTSTRAP.read_bytes()
    assert b"\r\n" not in raw, "the VM runs this with bash; CRLF line endings break it"
    script = raw.decode("utf-8")
    assert script.startswith("#!/usr/bin/env bash\n")
    assert "set -euo pipefail" in script
    # Docker Engine and the compose plugin from Docker's apt repository, for any architecture.
    assert "https://download.docker.com/linux/ubuntu" in script
    assert "arch=$(dpkg --print-architecture)" in script
    assert "docker-compose-plugin" in script
    # Clone or fast-forward only; never a reset or force.
    assert "git clone" in script and "merge --ff-only" in script
    for forbidden in ("reset --hard", "push", "--force", "clean -"):
        assert forbidden not in script, forbidden
    # Built on the VM, so the image matches its CPU.
    assert 'docker build --quiet -t "$IMAGE" .' in script
    # Env files: created only when absent, random password, private permissions.
    assert "openssl rand -hex 24" in script
    assert "umask 077" in script
    assert "[ ! -f deploy/postgres.env ] || [ ! -f deploy/judge.env ]" in script
    assert "NEBIUS_API_KEY=" in script and "NEBIUS_API_KEY=$" not in script
    # Assistants stay off unless the operator turns them on.
    assert "SHIFTGUARD_AGENT_ENABLED=false" in script
    assert "SHIFTGUARD_GENERAL_CHAT_ENABLED=false" in script
    # The dataset comes from a copy or from the hash-checked UCI download.
    assert "--dataset-from" in script
    assert "/src/scripts/download_datasets.py --dataset bank" in script
    assert "bank-additional-full.csv" in script and "bank-marketing.manifest.json" in script
    assert "docker compose -f deploy/compose.judge.yaml up -d" in script
    # The password is only ever written into the two env files, never to the terminal.
    for line in script.splitlines():
        if "$password" in line and "password=" not in line:
            assert line.rstrip().endswith(("> deploy/postgres.env", "> deploy/judge.env")), line
        if line.strip().startswith(("log ", "echo ")):
            for marker in ("$password", "SHIFTGUARD_DB_URL", "NEBIUS_API_KEY", "postgresql://"):
                assert marker not in line, line


def test_compose_interpolation_file_and_secrets_stay_out_of_git_and_the_image():
    ignored = (APP_ROOT / ".dockerignore").read_text(encoding="utf-8").split()
    assert "deploy/.env" in ignored
    gitignore = (APP_ROOT / ".gitignore").read_text(encoding="utf-8").split()
    assert ".env" in gitignore  # matches deploy/.env too


def test_dockerfile_runs_nonroot_single_worker_and_excludes_local_state():
    dockerfile = (APP_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "USER shiftguard" in dockerfile
    assert '"--workers", "1"' in dockerfile
    assert "HEALTHCHECK" in dockerfile
    ignored = (APP_ROOT / ".dockerignore").read_text(encoding="utf-8").split()
    for entry in (".env", "var", "deploy/judge.env", "deploy/postgres.env", "deploy/datasets"):
        assert entry in ignored


def test_env_example_carries_no_credentials():
    deploy = APP_ROOT / "deploy"
    for path in (APP_ROOT / ".env.example", deploy / "judge.env.example", deploy / "postgres.env.example"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            if name in {"NEBIUS_API_KEY", "POSTGRES_PASSWORD"}:
                assert value in {"", "replace-me"}, name
            if name == "SHIFTGUARD_DB_URL" and value.startswith("postgresql"):
                assert "replace-me" in value


# --- offline acceptance probe -------------------------------------------------

def _load_probe():
    spec = importlib.util.spec_from_file_location("check_hosted_release", APP_ROOT / "scripts" / "check_hosted_release.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_probe_report_redacts_capabilities_and_never_calls_chat():
    probe = _load_probe()
    calls = []

    def transport(method, path, *, body=None, headers=None):
        calls.append((method, path))
        if path == "/api/v1/agent/sessions":
            return 201, {"session_id": "s-1", "capability_token": "capability-secret"}
        return 404, {"error": {"code": "NOT_FOUND"}}

    report = probe.run_probe(transport, preset="bank-baseline", timeout_seconds=1, poll_seconds=0.01)
    assert report["status"] == "FAIL"
    assert "capability-secret" not in json.dumps(report)
    assert not any("/chat/" in path or "/agent/requests" in path for _method, path in calls)


def test_probe_completes_a_real_manual_bank_workflow(tmp_path):
    """The probe drives the real API and embedded worker; no fixture is inserted."""
    probe = _load_probe()
    settings = Settings(
        _env_file=None,
        db_url=f"sqlite:///{(tmp_path / 'probe.sqlite').as_posix()}",
        artifact_root=str(tmp_path / "artifacts"),
        embedded_worker=True,
        worker_poll_interval=0.2,
    )
    with TestClient(create_app(settings)) as client:
        report = probe.run_probe(probe.testclient_transport(client), preset="bank-baseline",
                                 timeout_seconds=900, poll_seconds=0.5)
    assert report["status"] == "PASS", json.dumps(report, indent=2)
    assert report["job"]["status"] == "completed"
    assert report["artifact"]["digest_matches_manifest"] is True
    assert {check["name"] for check in report["checks"]} >= {
        "live", "ready", "session", "missing_capability_rejected", "wrong_capability_rejected",
        "submit", "idempotent_replay", "job_completed", "experiment_listed", "artifact_digest",
    }
