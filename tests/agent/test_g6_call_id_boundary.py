from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from shiftguard.agent.registry import ToolRegistry
from shiftguard.agent.tools import ToolContext
from shiftguard.settings import Settings


@pytest.fixture
def tool_context(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/call_ids.db")
    return ToolContext(
        engine=engine,
        settings=Settings(SHIFTGUARD_DB_URL=f"sqlite:///{tmp_path}/call_ids.db"),
        session_id="call-id-test-session",
        request_id="call-id-test-request",
        ordinal=1,
    )


@pytest.mark.parametrize(
    "call_id",
    ["x", "a" * 65, "a" * 128, "a" * 256, "é" * 64, "é" * 128],
    ids=["one-byte", "ascii-65", "ascii-128", "ascii-256", "unicode-128-bytes", "unicode-256-bytes"],
)
def test_dispatch_preserves_opaque_call_id(call_id, tool_context):
    result = ToolRegistry().dispatch("inspect_dataset", {"dataset_id": "bank"}, tool_context, call_id)

    assert result.status == "success"
    assert result.tool_call_id == call_id


@pytest.mark.parametrize("call_id", ["", "\x00", "id\x00tail", "a" * 257, "é" * 129, "\ud800", None, 7, b"call"])
def test_invalid_call_id_is_rejected_before_handler(call_id, tool_context):
    registry = ToolRegistry()
    calls = []
    registry._tools["inspect_dataset"].handler = lambda *args: calls.append(args)

    result = registry.dispatch("inspect_dataset", {"dataset_id": "bank"}, tool_context, call_id)

    assert result.status == "error"
    assert calls == []
