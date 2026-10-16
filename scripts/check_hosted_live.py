"""One bounded live check of the hosted model path: one general-chat message and one
Results-assistant question about a saved Bank experiment.

usage: check_hosted_live.py --base-url URL --experiment-id ID --output PATH

Paid: uses at most 1 + 8 provider calls inside the server's own daily cap. The report keeps
status codes, sanitized usage, the ledger before/after, tool names and evidence references;
the capability token is never written. Model text is kept only as a short excerpt for review.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request
from uuid import uuid4


def call(base, method, path, body=None, headers=None, timeout=180):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(base + path, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as error:
        try:
            return error.code, json.loads(error.read() or b"null")
        except ValueError:
            return error.code, None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--results-prompt", default=None,
                        help="Results question; defaults to the exact selection command 'Summarize experiment <id>'")
    parser.add_argument("--skip-chat", action="store_true", help="only run the Results question")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite the report")
    base = args.base_url.rstrip("/")
    report = {"schema": "shiftguard.hosted-live-check.v1", "started_utc": datetime.now(timezone.utc).isoformat(),
              "base_url": base, "experiment_id": args.experiment_id}

    _, status = call(base, "GET", "/api/v1/agent/status")
    report["model"] = status.get("model")
    report["ledger_before"] = status.get("ordinary_budget")
    _, session = call(base, "POST", "/api/v1/agent/sessions", {})
    headers = {"X-Session-ID": session["session_id"], "X-Session-Token": session["capability_token"]}

    code, chat = (None, None) if args.skip_chat else call(base, "POST", "/api/v1/chat/messages", {
        "prompt": "In two sentences, what is probability calibration and why can missing input fields affect it?",
        "idempotency_key": "live-check-chat-" + uuid4().hex,
    }, headers)
    report["general_chat"] = {
        "http_status": code, "status": (chat or {}).get("status"),
        "usage": (chat or {}).get("usage"), "disclaimer": (chat or {}).get("disclaimer"),
        "reply_excerpt": ((chat or {}).get("reply") or "")[:300],
        "error_code": ((chat or {}).get("error") or (chat or {}).get("detail", {}).get("error") or {}).get("code") if isinstance(chat, dict) else None,
    }

    # Saved results are readable only through an exact selection command (Gate 7 authority).
    results_prompt = args.results_prompt or f"Summarize experiment {args.experiment_id}"
    report["results_prompt"] = results_prompt
    code, results = call(base, "POST", "/api/v1/agent/requests", {
        "prompt": results_prompt,
        "idempotency_key": "live-check-results-" + uuid4().hex,
    }, headers, timeout=600)
    results = results or {}
    final = results.get("final_response") or {}
    report["results_assistant"] = {
        "http_status": code, "status": results.get("status"), "call_count": results.get("call_count"),
        "turn_count": results.get("turn_count"),
        "tools": [entry.get("tool_name") or entry.get("name") for entry in results.get("tool_trace", [])],
        "evidence_refs": results.get("evidence_refs"),
        "final_excerpt": json.dumps(final)[:600],
        "error": results.get("error"),
        "guidance": final.get("guidance"),
        "claim_count": len(final.get("claims") or []),
        "final_response_bytes": len(json.dumps(final)),
    }
    _, status_after = call(base, "GET", "/api/v1/agent/status")
    report["ledger_after"] = status_after.get("ordinary_budget")
    before, after = report["ledger_before"] or {}, report["ledger_after"] or {}
    # Ledger delta: per-question cost only with --skip-chat, and only if no other visitor used
    # the shared allowance meanwhile.
    report["cost"] = {"calls": (after.get("calls_used") or 0) - (before.get("calls_used") or 0),
                      "tokens": (after.get("tokens_committed") or 0) - (before.get("tokens_committed") or 0),
                      "scope": "results question only" if args.skip_chat else "general chat + results question"}
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    # A grounded answer: completed, no refusal guidance, the selected experiment bound as
    # evidence and referenced by the rendered response, and at least one rendered claim.
    grounded = bool(
        report["results_assistant"]["status"] == "COMPLETED"
        and not final.get("guidance")
        and results.get("evidence_refs") == [args.experiment_id.lower()]
        and args.experiment_id.lower() in (final.get("evidence_references") or [])
        and final.get("claims")
    )
    report["results_grounded"] = grounded
    report["pass"] = bool((args.skip_chat or report["general_chat"]["http_status"] == 200) and grounded)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("pass", "results_grounded", "cost", "ledger_after")}, indent=2))
    print(json.dumps({"chat": report["general_chat"], "results": report["results_assistant"]}, indent=2)[:2500])
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
