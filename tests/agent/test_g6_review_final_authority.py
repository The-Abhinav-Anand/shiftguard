from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import pytest
from sqlalchemy import text

from shiftguard.agent.provider import ScriptedProvider
from test_luna_g6_protocol import (
    _call, _complete_published, _controller, _request, _response, protocol_env,
)


@pytest.mark.parametrize("authority_change", ["expire", "rotate", "unchanged"])
def test_terminal_receipt_is_bound_to_current_authority(protocol_env, monkeypatch, authority_change):
    env = protocol_env
    req = _request(env)
    provider = ScriptedProvider([
        _response(_call("run_experiment", {"preset_name": "bank-baseline"}, "authority-run")),
        _response(content=json.dumps({"template": "summary", "condition_refs": []})),
    ])
    control = _controller(env, provider)
    waiting = asyncio.run(control.execute_request(req.id, "authority-first"))
    assert waiting.status == "WAITING_FOR_JOB" and waiting.active_nonce
    _complete_published(env, waiting.active_job_id)
    original_finish = env["store"].finish_request
    changed = False

    def finish_after_authority_change(*args, **kwargs):
        nonlocal changed
        if not changed:
            changed = True
            with env["engine"].begin() as conn:
                if authority_change == "expire":
                    conn.execute(text("UPDATE agent_sessions SET status='EXPIRED' WHERE id=:id"), {"id": env["session"].id})
                elif authority_change == "rotate":
                    conn.execute(text("UPDATE agent_sessions SET capability_token=:token WHERE id=:id"), {"id": env["session"].id, "token": uuid4().hex})
        return original_finish(*args, **kwargs)

    monkeypatch.setattr(env["store"], "finish_request", finish_after_authority_change)
    code, body = asyncio.run(control.resume_request(req.id, waiting.active_nonce, "authority-resume"))
    receipt = env["store"].get_receipt(req.id, waiting.active_nonce)
    assert receipt is not None and receipt.status_code == code
    assert receipt.response == body
    if authority_change == "unchanged":
        assert code == 200 and body["status"] == "COMPLETED"
    else:
        assert code == 500 and body["status"] == "FAILED"
        assert body["error"]["code"] == "UNAUTHORIZED_SESSION"
        assert not env["store"].verify_request_authority(req.id, env["session"].capability_token)
