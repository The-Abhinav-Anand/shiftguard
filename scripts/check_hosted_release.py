"""Offline hosted-release acceptance probe for a running SHIFTGUARD deployment.

usage: check_hosted_release.py --base-url URL --output PATH [--preset NAME] [--timeout SECONDS]

It creates its own session, checks capability enforcement, submits one approved
Bank preset, waits for the separate worker to publish it, and compares one
published artifact's bytes with the stored manifest digest. It never sends a
chat prompt or a Results-assistant request, so it spends no model budget.
The report keeps ids, statuses and hashes only; capabilities are never written.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any, Callable
import urllib.error
import urllib.request
from uuid import uuid4


Transport = Callable[..., tuple[int, Any]]
TERMINAL = {"completed", "failed", "cancelled"}
PRESETS = ("bank-baseline", "bank-outage-50", "bank-stress")


def urllib_transport(base_url: str, *, timeout: float = 30.0) -> Transport:
    base = base_url.rstrip("/")

    def send(method: str, path: str, *, body: Any = None, headers: dict[str, str] | None = None,
             raw: bool = False):
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(base + path, data=data, method=method)
        request.add_header("Accept", "application/json")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        for name, value in (headers or {}).items():
            request.add_header(name, value)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, _decode(response.read(), response.headers.get("Content-Type", ""), raw)
        except urllib.error.HTTPError as error:
            return error.code, _decode(error.read(), error.headers.get("Content-Type", ""), raw)

    return send


def testclient_transport(client) -> Transport:
    def send(method: str, path: str, *, body: Any = None, headers: dict[str, str] | None = None,
             raw: bool = False):
        response = client.request(method, path, json=body, headers=headers or {})
        return response.status_code, _decode(response.content, response.headers.get("content-type", ""), raw)

    return send


def _decode(content: bytes, content_type: str, raw: bool = False) -> Any:
    """Exact bytes when ``raw`` (artifact digests), otherwise parsed JSON."""
    if raw or "json" not in content_type:
        return content
    try:
        return json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None


def _code(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    error = body.get("error")
    if not isinstance(error, dict) and isinstance(body.get("detail"), dict):
        error = body["detail"].get("error")
    return error.get("code") if isinstance(error, dict) and isinstance(error.get("code"), str) else None


def run_probe(transport: Transport, *, preset: str, timeout_seconds: float, poll_seconds: float) -> dict[str, Any]:
    if preset not in PRESETS:
        raise ValueError(f"preset must be one of {PRESETS}")
    report: dict[str, Any] = {
        "schema": "shiftguard.hosted-release-probe.v1",
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "preset": preset,
        "model_requests_sent": 0,
        "checks": [],
        "job": None,
        "experiment_id": None,
        "artifact": None,
    }

    def check(name: str, passed: bool, detail: Any = None) -> bool:
        report["checks"].append({"name": name, "passed": bool(passed), "detail": detail})
        return bool(passed)

    def finish() -> dict[str, Any]:
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        report["status"] = "PASS" if report["checks"] and all(c["passed"] for c in report["checks"]) else "FAIL"
        return report

    status, body = transport("GET", "/health/live")
    check("live", status == 200 and body == {"status": "ok"}, {"http_status": status})
    status, body = transport("GET", "/health/ready")
    check("ready", status == 200 and isinstance(body, dict) and body.get("dataset") == "verified",
          {"http_status": status, "reason": body.get("error", {}).get("details") if isinstance(body, dict) else None})

    status, body = transport("POST", "/api/v1/agent/sessions", body={})
    session_ok = status == 201 and isinstance(body, dict) and isinstance(body.get("session_id"), str) \
        and isinstance(body.get("capability_token"), str)
    if not check("session", session_ok, {"http_status": status}):
        return finish()
    session_id, capability = body["session_id"], body["capability_token"]
    headers = {"X-Session-ID": session_id, "X-Session-Token": capability}
    payload = {"preset_name": preset}

    status, body = transport("POST", "/api/v1/experiments", body=payload)
    check("missing_capability_rejected", status == 401, {"http_status": status, "code": _code(body)})
    status, body = transport("POST", "/api/v1/experiments", body=payload,
                             headers={"X-Session-ID": session_id, "X-Session-Token": "wrong-" + uuid4().hex})
    check("wrong_capability_rejected", status == 401, {"http_status": status, "code": _code(body)})

    key = "release-probe-" + uuid4().hex
    status, body = transport("POST", "/api/v1/experiments", body=payload, headers={**headers, "Idempotency-Key": key})
    if not check("submit", status == 202 and isinstance(body, dict) and isinstance(body.get("job_id"), str),
                 {"http_status": status, "code": _code(body)}):
        return finish()
    job_id = body["job_id"]
    status, body = transport("POST", "/api/v1/experiments", body=payload, headers={**headers, "Idempotency-Key": key})
    check("idempotent_replay", status == 202 and isinstance(body, dict) and body.get("job_id") == job_id,
          {"http_status": status})

    deadline = time.monotonic() + timeout_seconds
    observed: list[str] = []
    job: dict[str, Any] = {}
    while True:
        status, body = transport("GET", f"/api/v1/jobs/{job_id}", headers=headers)
        job = body if status == 200 and isinstance(body, dict) else {}
        state = job.get("status")
        if isinstance(state, str) and (not observed or observed[-1] != state):
            observed.append(state)
        if state in TERMINAL or time.monotonic() > deadline:
            break
        time.sleep(poll_seconds)
    report["job"] = {"id": job_id, "status": job.get("status"), "observed": observed,
                     "attempt": job.get("attempt"), "error_code": (job.get("error") or {}).get("code")}
    if not check("job_completed", job.get("status") == "completed" and isinstance(job.get("experiment_id"), str),
                 {"observed": observed}):
        return finish()
    experiment_id = job["experiment_id"]
    report["experiment_id"] = experiment_id

    status, listing = transport("GET", "/api/v1/experiments?limit=50")
    status_one, overview = transport("GET", f"/api/v1/experiments/{experiment_id}")
    listed = status == 200 and any(item.get("experiment_id") == experiment_id
                                   for item in (listing or {}).get("experiments", []) if isinstance(item, dict))
    check("experiment_listed", listed and status_one == 200, {"http_status": [status, status_one]})

    status, artifacts = transport("GET", f"/api/v1/experiments/{experiment_id}/artifacts")
    entries = (artifacts or {}).get("artifacts", []) if status == 200 and isinstance(artifacts, dict) else []
    entry = next((item for item in entries if isinstance(item, dict) and item.get("sha256")), None)
    if not check("artifact_listed", entry is not None, {"http_status": status, "count": len(entries)}):
        return finish()
    status, content = transport("GET", entry["download_url"], raw=True)
    actual = hashlib.sha256(content).hexdigest() if status == 200 and isinstance(content, bytes) else None
    report["artifact"] = {"name": entry.get("name"), "manifest_sha256": entry["sha256"], "sha256": actual,
                          "digest_matches_manifest": actual == entry["sha256"]}
    check("artifact_digest", status == 200 and actual == entry["sha256"], {"http_status": status})
    return finish()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--preset", default="bank-baseline", choices=PRESETS)
    parser.add_argument("--timeout", default=1800.0, type=float)
    parser.add_argument("--poll", default=2.0, type=float)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error(f"refusing to overwrite {args.output}")
    report = run_probe(urllib_transport(args.base_url), preset=args.preset,
                       timeout_seconds=args.timeout, poll_seconds=args.poll)
    report["base_url"] = args.base_url.split("@")[-1]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "experiment_id": report["experiment_id"],
                      "failed": [c["name"] for c in report["checks"] if not c["passed"]]}))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
