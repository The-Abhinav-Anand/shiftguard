"""OR-09: request validation errors are JSON-safe, bounded and never echo input."""

from __future__ import annotations

import json

import pytest
from starlette.testclient import TestClient

from shiftguard.api.main import create_app
from shiftguard.settings import Settings


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        _env_file=None,
        db_url=f"sqlite:///{(tmp_path / 'validation.sqlite').as_posix()}",
        artifact_root=str(tmp_path / "artifacts"),
        general_chat_enabled=True,
    )
    with TestClient(create_app(settings), raise_server_exceptions=False) as test_client:
        yield test_client


def _session_headers(client) -> dict[str, str]:
    session = client.post("/api/v1/agent/sessions", json={}).json()
    return {"X-Session-ID": session["session_id"], "X-Session-Token": session["capability_token"]}


def _assert_public_shape(response, *, secrets: tuple[str, ...] = ()) -> list[dict]:
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["request_id"]
    assert error["request_id"] == response.headers["X-Request-ID"]
    errors = error["details"]["errors"]
    assert 1 <= len(errors) <= 20
    for item in errors:
        assert set(item) == {"loc", "type", "msg"}
        assert isinstance(item["type"], str) and isinstance(item["msg"], str)
        assert all(isinstance(part, (str, int)) for part in item["loc"])
    for secret in secrets:
        assert secret not in response.text
    return errors


@pytest.mark.parametrize(
    ("field", "body"),
    [
        ("prompt", {"prompt": "   \t ", "idempotency_key": "blank-prompt"}),
        ("idempotency_key", {"prompt": "hello", "idempotency_key": "   "}),
    ],
)
def test_custom_blank_validator_returns_422_not_500(client, field, body):
    headers = _session_headers(client)
    response = client.post("/api/v1/chat/messages", json=body, headers=headers)
    errors = _assert_public_shape(response, secrets=(headers["X-Session-Token"],))
    assert errors[0]["loc"] == ["body", field]
    assert errors[0]["type"] == "value_error"


def test_ordinary_field_errors_keep_their_location_and_type(client):
    headers = _session_headers(client)
    response = client.post(
        "/api/v1/chat/messages",
        json={"prompt": 7, "idempotency_key": "typed"},
        headers=headers,
    )
    errors = _assert_public_shape(response)
    assert errors[0]["loc"] == ["body", "prompt"]
    assert errors[0]["type"] == "string_type"


def test_extra_and_oversized_fields_do_not_echo_submitted_text(client):
    headers = _session_headers(client)
    marker = "é中\U0001f600-private-prompt-" + "x" * 4001
    response = client.post(
        "/api/v1/chat/messages",
        json={"prompt": marker, "idempotency_key": "big", "smuggled": "private-extra-value"},
        headers=headers,
    )
    errors = _assert_public_shape(
        response, secrets=("private-prompt", "private-extra-value", headers["X-Session-Token"])
    )
    assert {item["type"] for item in errors} == {"string_too_long", "extra_forbidden"}


def test_nested_validation_errors_are_bounded(client):
    headers = _session_headers(client)
    response = client.post(
        "/api/v1/experiments",
        json={"preset_name": "bank-outage-50", "config": {f"field_{i}": i for i in range(40)}},
        headers=headers,
    )
    errors = _assert_public_shape(response)
    assert len(errors) <= 20


def test_malformed_json_body_is_a_json_safe_client_error(client):
    headers = {**_session_headers(client), "Content-Type": "application/json"}
    response = client.post("/api/v1/chat/messages", content=b'{"prompt": "unterminated', headers=headers)
    _assert_public_shape(response)
    json.dumps(response.json())
