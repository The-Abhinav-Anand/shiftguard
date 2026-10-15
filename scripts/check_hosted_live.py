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

    code, chat = call(base, "POST", "/api/v1/chat/messages", {
        "prompt": "In two sentences, what is probability calibration and why can missing input fields affect it?",
        "idempotency_key": "live-check-chat-" + uuid4().hex,
    }, headers)
    report["general_chat"] = {
        "http_status": code, "status": (chat or {}).get("status"),
        "usage": (chat or {}).get("usage"), "disclaimer": (chat or {}).get("disclaimer"),
        "reply_excerpt": ((chat or {}).get("reply") or "")[:300],
        "error_code": ((chat or {}).get("error") or (chat or {}).get("detail", {}).get("error") or {}).get("code") if isinstance(chat, dict) else None,
    }

    code, results = call(base, "POST", "/api/v1/agent/requests", {
        "prompt": f"For saved experiment {args.experiment_id}, summarize the budget-50 comparison between "
                  "target temperature and the source-only comparator. Use only the saved record.",
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
    }
    _, status_after = call(base, "GET", "/api/v1/agent/status")
    report["ledger_after"] = status_after.get("ordinary_budget")
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    report["pass"] = bool(report["general_chat"]["http_status"] == 200
                          and report["results_assistant"]["status"] == "COMPLETED")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("pass", "ledger_before", "ledger_after")}, indent=2))
    print(json.dumps({"chat": report["general_chat"], "results": report["results_assistant"]}, indent=2)[:2500])
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
