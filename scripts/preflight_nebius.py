"""Offline-by-default, allowance-bounded Nebius/Nemotron preflight."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from typing import Any, Callable, Literal
from urllib.parse import urlsplit

from shiftguard.agent.provider import ProviderResponse, _parse_provider_response
from shiftguard.agent.rendering import parse_explanation_plan
from shiftguard.agent.schemas import InspectDatasetParams
from shiftguard.settings import Settings

EXPECTED_MODEL = "nvidia/Nemotron-3_5-Lightning"
EXPECTED_PROVIDER = "nebius"
MAX_LIVE_OUTPUT_TOKENS = 256
PREFLIGHT_TIMEOUT_SECONDS = 20.0
OFFLINE_FAKE_TEST_KIND = "offline_injected_fake"
SAFE_FINISH_REASONS = frozenset({"stop", "length", "tool_calls", "content_filter", "function_call"})
TestKind = Literal["provider_live_canary", "offline_inspection", "offline_injected_fake"]
CANARY_AUTHORIZED_CONDITION_REFS: frozenset[str] = frozenset()
VALID_TEST_KINDS = frozenset({"provider_live_canary", "offline_inspection", OFFLINE_FAKE_TEST_KIND})


def _write_evidence(path: str | None, evidence: dict[str, Any]) -> None:
    if path is None:
        return
    target = os.path.abspath(path)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(evidence, stream, indent=2, sort_keys=True)
        stream.write("\n")


def _safe_endpoint_host(base_url: str) -> str | None:
    try:
        return urlsplit(base_url).hostname
    except ValueError:
        return None


def _estimate_input_upper_bound(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None) -> int:
    # UTF-8 bytes are a conservative token upper bound for the ASCII canary payloads;
    # add fixed framing overhead for the chat envelope and tool schemas.
    payload = {"messages": messages, "tools": tools or []}
    byte_count = len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    return byte_count + 256


def _safe_response_diagnostics(response: ProviderResponse) -> dict[str, Any]:
    usage = response.usage or {}
    finish_reason = response.finish_reason
    if not isinstance(finish_reason, str) or finish_reason not in SAFE_FINISH_REASONS:
        finish_reason = None
    return {
        "finish_reason": finish_reason,
        "content_present": response.content is not None,
        "content_length": len(response.content) if response.content is not None else 0,
        "usage": {
            name: usage[name]
            for name in ("prompt_tokens", "completion_tokens", "reasoning_tokens")
            if isinstance(usage.get(name), int) and not isinstance(usage.get(name), bool)
        },
    }


def _validated_canary_facts() -> dict[str, str]:
    """Build the fixed metadata-only tool result owned by this Python canary."""
    params = InspectDatasetParams.model_validate({"dataset_id": "bank"})
    return {"dataset_id": params.dataset_id, "canary": "metadata-only"}


def validate_explanation_plan(content: str | None) -> tuple[bool, str | None]:
    """Use the runtime parser; this canary authorizes no empirical condition IDs."""
    plan = parse_explanation_plan(content, CANARY_AUTHORIZED_CONDITION_REFS)
    if plan is None:
        return False, None
    return True, "strict_explanation_plan"


def build_tool_exchange_messages(tool_call: Any) -> list[dict[str, Any]]:
    call_id = getattr(tool_call, "id", None)
    function = getattr(tool_call, "function", None)
    if not isinstance(call_id, str) or not call_id or getattr(function, "name", None) != "inspect_dataset":
        raise ValueError("invalid original tool call")
    arguments = getattr(function, "arguments", None)
    if not isinstance(arguments, str) or json.loads(arguments) != {"dataset_id": "bank"}:
        raise ValueError("invalid original tool arguments")
    assistant_call = tool_call.model_dump()
    canary_facts = _validated_canary_facts()
    tool_reply = {
        "role": "tool",
        "tool_call_id": call_id,
        "name": "inspect_dataset",
        "content": json.dumps(canary_facts, separators=(",", ":")),
    }
    if assistant_call.get("id") != tool_reply["tool_call_id"]:
        raise ValueError("tool response does not match original call id")
    return [
        {"role": "user", "content": "Inspect bank and produce a short evidence-bound explanation plan."},
        {"role": "assistant", "content": None, "tool_calls": [assistant_call]},
        tool_reply,
        {
            "role": "user",
            "content": (
                "Return JSON only as a strict explanation plan with exactly the keys template and condition_refs. "
                "Allowed templates: summary, comparisons, failures, fallbacks, costs. "
                "condition_refs must be an empty array because this metadata-only canary has no empirical condition IDs. "
                "Do not include prose, numbers, claims, or additional keys."
            ),
        },
    ]


class _Allowance:
    def __init__(self, max_calls: int, max_tokens: int) -> None:
        self.max_calls = max_calls
        self.max_tokens = max_tokens
        self.calls_made = 0
        self.reserved_tokens = 0
        self.reported_tokens = 0
        self.last_reservation = 0
        self.failure: str | None = None

    def reserve(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None, output_limit: int) -> bool:
        if self.calls_made >= self.max_calls:
            self.failure = "CALL_ALLOWANCE_EXHAUSTED"
            return False
        reservation = _estimate_input_upper_bound(messages, tools) + output_limit
        if self.reserved_tokens + reservation > self.max_tokens:
            self.failure = "TOKEN_ALLOWANCE_INSUFFICIENT_FOR_NEXT_CALL"
            return False
        self.reserved_tokens += reservation
        self.last_reservation = reservation
        self.calls_made += 1
        return True

    def record_usage(self, response: ProviderResponse) -> bool:
        if response.usage is None:
            self.failure = "USAGE_MISSING"
            return False
        used = response.usage["total_tokens"]
        self.reported_tokens += used
        if used > self.max_tokens or self.reported_tokens > self.max_tokens:
            self.failure = "REPORTED_USAGE_EXCEEDS_ALLOWANCE"
            return False
        # Keep the full conservative reservation. Usage never releases capacity.
        if used > self.last_reservation:
            extra = used - self.last_reservation
            if self.reserved_tokens + extra > self.max_tokens:
                self.failure = "REPORTED_USAGE_EXCEEDS_ALLOWANCE"
                return False
            self.reserved_tokens += extra
        return True


async def run_preflight(
    live: bool,
    max_calls: int,
    max_tokens: int,
    evidence_path: str | None,
    requested_model: str | None = None,
    *,
    client_factory: Callable[..., Any] | None = None,
    test_kind: TestKind | None = None,
) -> int:
    provider_settings = Settings(_env_file=None)
    api_key = os.getenv("NEBIUS_API_KEY", "").strip()
    base_url = os.getenv("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1").strip()
    configured_model = os.getenv("NEBIUS_MODEL", EXPECTED_MODEL).strip()
    selected_test_kind: TestKind = (
        test_kind if test_kind is not None else (
            OFFLINE_FAKE_TEST_KIND if client_factory is not None
            else "provider_live_canary" if live
            else "offline_inspection"
        )
    )
    evidence: dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": "offline_test" if selected_test_kind == OFFLINE_FAKE_TEST_KIND else ("live" if live else "offline"),
        "provider": EXPECTED_PROVIDER,
        "model_expected": EXPECTED_MODEL,
        "model_requested": requested_model,
        "endpoint_host": _safe_endpoint_host(base_url),
        "model_configured": configured_model,
        "thinking_setting_enabled": provider_settings.nebius_enable_thinking,
        "test_kind": selected_test_kind,
        "key_present": bool(api_key),
        "sdk_retries": 0,
        "wire_attempts": 0,
        "canaries": {},
    }
    print("Nebius preflight: endpoint configuration inspected; credentials are not displayed.")
    print(f"  Model configured: {configured_model}")
    print(f"  Test kind: {selected_test_kind}")

    if selected_test_kind not in VALID_TEST_KINDS:
        evidence.update(status="INVALID_TEST_KIND", failure="UNKNOWN_TEST_KIND")
        _write_evidence(evidence_path, evidence)
        return 1
    if client_factory is not None and selected_test_kind != OFFLINE_FAKE_TEST_KIND:
        evidence.update(status="INVALID_TEST_KIND", failure="INJECTED_CLIENT_REQUIRES_OFFLINE_TEST_KIND")
        _write_evidence(evidence_path, evidence)
        return 1
    if selected_test_kind == OFFLINE_FAKE_TEST_KIND and (not live or client_factory is None):
        evidence.update(status="INVALID_TEST_KIND", failure="OFFLINE_FAKE_TEST_REQUIRES_INJECTED_CLIENT")
        _write_evidence(evidence_path, evidence)
        return 1
    if selected_test_kind == "provider_live_canary" and not live:
        evidence.update(status="INVALID_TEST_KIND", failure="LIVE_PROVIDER_TEST_REQUIRES_LIVE_MODE")
        _write_evidence(evidence_path, evidence)
        return 1
    if selected_test_kind == "offline_inspection" and live:
        evidence.update(status="INVALID_TEST_KIND", failure="OFFLINE_INSPECTION_CANNOT_RUN_LIVE_CANARIES")
        _write_evidence(evidence_path, evidence)
        return 1

    if not live:
        evidence["status"] = "OFFLINE_INSPECTION_PASSED"
        _write_evidence(evidence_path, evidence)
        return 0

    if not api_key:
        evidence.update(status="BLOCKED_REQUIRED_LIVE_EVIDENCE", failure="API_KEY_MISSING")
        _write_evidence(evidence_path, evidence)
        return 2
    if max_calls <= 0 or max_tokens <= 0:
        evidence.update(status="INVALID_ALLOWANCE", failure="POSITIVE_CALL_AND_TOKEN_ALLOWANCES_REQUIRED")
        _write_evidence(evidence_path, evidence)
        return 1
    if requested_model != EXPECTED_MODEL or configured_model != EXPECTED_MODEL:
        evidence.update(status="INVALID_MODEL", failure="EXACT_MODEL_CONFIRMATION_REQUIRED")
        _write_evidence(evidence_path, evidence)
        return 1

    allowance = _Allowance(max_calls=max_calls, max_tokens=max_tokens)
    client = None
    try:
        if client_factory is None:
            from openai import AsyncOpenAI

            client_factory = AsyncOpenAI
        client = client_factory(
            api_key=api_key,
            base_url=base_url,
            timeout=PREFLIGHT_TIMEOUT_SECONDS,
            max_retries=0,
        )

        async def call_canary(
            key: str,
            messages: list[dict[str, Any]],
            *,
            output_limit: int,
            tools: list[dict[str, Any]] | None = None,
            tool_choice: Any = None,
        ) -> ProviderResponse | None:
            if not allowance.reserve(messages, tools, output_limit):
                evidence["failure"] = allowance.failure
                evidence["canaries"][key] = {"status": "NOT_RUN", "failure": allowance.failure}
                return None
            kwargs: dict[str, Any] = {
                "model": EXPECTED_MODEL,
                "messages": messages,
                "max_tokens": output_limit,
                "extra_body": {"chat_template_kwargs": provider_settings.nebius_chat_template_kwargs},
            }
            if tools:
                kwargs.update(tools=tools, tool_choice=tool_choice or "auto")
            evidence["wire_attempts"] += 1
            started = time.monotonic()
            try:
                async with asyncio.timeout(PREFLIGHT_TIMEOUT_SECONDS):
                    raw = await client.chat.completions.create(**kwargs)
                parsed = _parse_provider_response(raw, expected_model=EXPECTED_MODEL)
                diagnostics = _safe_response_diagnostics(parsed)
            except Exception as exc:
                evidence["canaries"][key] = {
                    "status": "FAIL",
                    "failure": "PROVIDER_TIMEOUT" if isinstance(exc, TimeoutError) or type(exc).__name__ == "APITimeoutError" else "PROVIDER_OR_RESPONSE_ERROR",
                    "error_type": type(exc).__name__,
                    "latency_seconds": round(time.monotonic() - started, 3),
                }
                evidence["failure"] = "REQUIRED_CANARY_FAILED"
                return None
            if not allowance.record_usage(parsed):
                evidence["canaries"][key] = {
                    "status": "FAIL",
                    "failure": allowance.failure,
                    "diagnostics": diagnostics,
                    "latency_seconds": round(time.monotonic() - started, 3),
                }
                evidence["failure"] = allowance.failure
                return None
            evidence["canaries"][key] = {
                "status": "PASS_PENDING_VALIDATION",
                "model_returned": getattr(raw, "model", None),
                "usage_tokens": parsed.usage["total_tokens"],
                "diagnostics": diagnostics,
                "latency_seconds": round(time.monotonic() - started, 3),
            }
            return parsed

        ping = await call_canary(
            "chat_ping",
            [{"role": "user", "content": "Reply with exactly PONG."}],
            output_limit=16,
        )
        if ping is None:
            raise RuntimeError("chat ping was not completed")
        ping_ok = ping.content is not None and ping.content.strip() == "PONG" and not ping.tool_calls
        evidence["canaries"]["chat_ping"].update(
            status="PASS" if ping_ok else "FAIL",
            exact_pong=ping_ok,
        )
        if not ping_ok:
            evidence["failure"] = "PING_CONTENT_INVALID"
            raise RuntimeError("chat ping canary failed")

        inspect_tool = [{
            "type": "function",
            "function": {
                "name": "inspect_dataset",
                "description": "Inspect only the named public dataset.",
                "parameters": {
                    "type": "object",
                    "properties": {"dataset_id": {"type": "string", "enum": ["bank"]}},
                    "required": ["dataset_id"],
                    "additionalProperties": False,
                },
            },
        }]
        tool_response = await call_canary(
            "tool_calling",
            [{"role": "user", "content": "Call inspect_dataset with dataset_id bank."}],
            output_limit=128,
            tools=inspect_tool,
            tool_choice="required",
        )
        if tool_response is None:
            raise RuntimeError("tool-call canary was not completed")
        valid_tool = False
        call_id: str | None = None
        if tool_response.content is None and tool_response.tool_calls and len(tool_response.tool_calls) == 1:
            call = tool_response.tool_calls[0]
            call_id = call.id
            try:
                arguments = json.loads(call.function.arguments)
            except (TypeError, json.JSONDecodeError):
                arguments = None
            valid_tool = (
                call.function.name == "inspect_dataset"
                and isinstance(arguments, dict)
                and arguments == {"dataset_id": "bank"}
            )
        evidence["canaries"]["tool_calling"].update(
            status="PASS" if valid_tool else "FAIL",
            exact_tool_name=bool(valid_tool),
            exact_arguments=bool(valid_tool),
            original_call_id_present=bool(call_id),
        )
        if not valid_tool or call_id is None:
            evidence["failure"] = "TOOL_CALL_INVALID"
            raise RuntimeError("tool-call canary failed")

        plan_messages = build_tool_exchange_messages(tool_response.tool_calls[0])
        plan = await call_canary("tool_exchange_and_explanation", plan_messages, output_limit=256)
        if plan is None:
            raise RuntimeError("tool-exchange/plan canary was not completed")
        valid_plan, plan_mode = validate_explanation_plan(plan.content)
        evidence["canaries"]["tool_exchange_and_explanation"].update(
            status="PASS" if valid_plan else "FAIL",
            original_call_id_exchange=(plan_messages[1]["tool_calls"][0]["id"] == plan_messages[2]["tool_call_id"]),
            explanation_mode=plan_mode,
            fact_source="python_owned_metadata_only",
            authorized_condition_refs=sorted(CANARY_AUTHORIZED_CONDITION_REFS),
        )
        if not valid_plan:
            evidence["failure"] = "STRICT_EXPLANATION_PLAN_INVALID"
            raise RuntimeError("strict explanation-plan canary failed")

        evidence["reserved_tokens"] = allowance.reserved_tokens
        evidence["reported_tokens"] = allowance.reported_tokens
        evidence["total_calls_made"] = allowance.calls_made
        evidence["status"] = (
            "OFFLINE_TEST_CANARIES_PASSED"
            if selected_test_kind == OFFLINE_FAKE_TEST_KIND
            else "LIVE_CANARIES_PASSED"
        )
        _write_evidence(evidence_path, evidence)
        return 0
    except Exception:
        evidence.setdefault("failure", "REQUIRED_CANARY_FAILED")
        evidence["status"] = (
            "OFFLINE_TEST_CANARY_FAILED"
            if selected_test_kind == OFFLINE_FAKE_TEST_KIND
            else "LIVE_CANARY_FAILED"
        )
        evidence["reserved_tokens"] = allowance.reserved_tokens
        evidence["reported_tokens"] = allowance.reported_tokens
        evidence["total_calls_made"] = allowance.calls_made
        _write_evidence(evidence_path, evidence)
        return 1
    finally:
        if client is not None:
            await client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline-by-default SHIFTGUARD Nebius preflight")
    parser.add_argument("--live", action="store_true", help="Run bounded live canaries; requires exact model and explicit allowances")
    parser.add_argument("--model", default=None, help="Exact model confirmation required with --live")
    parser.add_argument("--allow-calls", type=int, default=0, help="Positive maximum logical/wire requests for live mode")
    parser.add_argument("--allow-tokens", type=int, default=0, help="Positive total token reservation for live mode")
    parser.add_argument("--write-redacted-evidence", default=None, help="Write redacted JSON evidence")
    args = parser.parse_args()
    result = asyncio.run(run_preflight(
        live=args.live,
        max_calls=args.allow_calls,
        max_tokens=args.allow_tokens,
        evidence_path=args.write_redacted_evidence,
        requested_model=args.model,
    ))
    sys.exit(result)


if __name__ == "__main__":
    main()
