"""C2 regressions for typed, sanitized public errors on terminal paths."""

from __future__ import annotations

import json

from shiftguard.agent.rendering import ResultRenderer
from shiftguard.agent.schemas import PublicToolError, ToolResult, ToolTraceEntry


def test_luna_g6_terminal_error_schema_canonicalizes_public_objects_and_legacy_strings():
    public = ToolResult(
        tool_name="run_experiment", tool_call_id="call-terminal", status="error",
        error={
            "code": "PUBLISHED_RESULT_UNVERIFIED",
            "message": "C:\\private\\api_key=do-not-persist",
            "worker_id": "worker-secret", "traceback": "C:\\private\\worker.log",
        },
    )
    assert isinstance(public.error, PublicToolError)
    assert public.model_dump(mode="json")["error"] == {
        "code": "PUBLISHED_RESULT_UNVERIFIED",
        "message": "Completed job publication could not be verified.",
    }

    legacy = ToolResult(
        tool_name="run_experiment", tool_call_id="call-legacy", status="error",
        error="INVALID_ARGUMENTS: C:\\private\\api_key=do-not-persist",
    )
    assert legacy.error == "INVALID_ARGUMENTS: Arguments were rejected."

    trace = ToolTraceEntry(
        ordinal=1, tool_name="run_experiment", tool_call_id="call-trace", arguments={},
        status="cancelled", error={"code": "JOB_CANCELLED", "message": "private path", "raw": "secret"},
    )
    assert trace.model_dump(mode="json")["error"] == {
        "code": "JOB_CANCELLED", "message": "The job was cancelled.",
    }


def test_luna_g6_project_tool_result_preserves_terminal_status_and_safe_code():
    result = ToolResult(
        tool_name="run_experiment", tool_call_id="call-published", status="error",
        error={"code": "PUBLISHED_RESULT_UNVERIFIED", "message": "C:\\private\\labels.csv", "details": {"key": "secret"}},
    )
    from shiftguard.agent.tools.projections import project_tool_result

    safe = project_tool_result(result).model_dump(mode="json")
    assert safe["status"] == "error"
    assert safe["error"] == {
        "code": "PUBLISHED_RESULT_UNVERIFIED",
        "message": "Completed job publication could not be verified.",
    }
    assert "private" not in json.dumps(safe)
    assert "details" not in json.dumps(safe)


def test_luna_g6_renderer_retains_sanitized_terminal_outcome_without_evidence():
    trace = [{
        "ordinal": 1, "tool_name": "run_experiment", "tool_call_id": "call-failed",
        "arguments": {}, "status": "failed",
        "error": {"code": "SYNTHETIC_FAILURE", "message": "C:\\private\\api_key=secret", "worker_id": "worker-secret"},
        "result": {
            "status": "failed",
            "error": {"code": "SYNTHETIC_FAILURE", "message": "C:\\private\\api_key=secret", "stack": "secret"},
        },
    }]
    rendered = ResultRenderer.render_from_tool_results("", trace, [])
    assert rendered["claims"] == []
    assert rendered["tool_errors"] == [{
        "tool_name": "run_experiment", "status": "failed",
        "code": "SYNTHETIC_FAILURE", "message": "The job failed.",
    }]
    assert "failed: SYNTHETIC_FAILURE: The job failed." in rendered["summary"]
    encoded = json.dumps(rendered)
    assert "private" not in encoded
    assert "api_key" not in encoded
    assert "worker-secret" not in encoded
    assert "stack" not in encoded
