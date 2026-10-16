"""Durable, fenced controller for bounded agent turns and tool continuations."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from typing import Any

from sqlalchemy.engine import Engine

from shiftguard.agent.policy import (
    MAX_REPAIRS_PER_SIGNATURE, MAX_TOOL_CALLS, MAX_TURNS, AgentErrorCode,
    APPROVED_BUDGETS, APPROVED_CALIBRATORS, APPROVED_PREDICTORS,
    APPROVED_SCENARIOS, SUPPORTED_COST_PAIRS, compute_repair_signature,
    normalized_repair_signature, safe_tool_call_id,
)
from shiftguard.agent.prompts import build_system_message
from shiftguard.agent.execution_authority import authorized_execution_presets
from shiftguard.agent.provider import (
    MAX_TRANSCRIPT_BYTES as MAX_PROVIDER_TRANSCRIPT_BYTES,
    ProviderClient, ProviderDisabledError, ProviderError,
)
from shiftguard.agent.registry import ToolRegistry, safe_arguments_for_storage, safe_tool_error
from shiftguard.agent.rendering import ResultRenderer
from shiftguard.agent.schemas import ToolResult, ToolTraceEntry
from shiftguard.agent.store import (
    AgentRequestRecord, AgentStore, IdempotencyConflictError, InvalidContinuationNonce,
    LeaseLostError, RequestAuthorityError,
)
from shiftguard.agent.tools import ToolContext
from shiftguard.jobs.queue import JobQueue
from shiftguard.settings import Settings
from shiftguard.storage.repositories import ExperimentRepository

logger = logging.getLogger(__name__)
MAX_ACCEPTED_TOOL_CALLS = 12
MAX_PROVIDER_ARGUMENT_BYTES = 8 * 1024
MAX_PROVIDER_CONTENT_BYTES = 16 * 1024
MAX_PROVIDER_DECISION_BYTES = 64 * 1024
# Model-facing tool messages are bounded digests; the stored execution keeps the full result.
MAX_MODEL_TOOL_MESSAGE_BYTES = 6 * 1024
MIN_MODEL_TOOL_MESSAGE_BYTES = 1024
# Bounds model context and the byte-based token reservation (input_token_upper_bound) of the
# provider copy. It is NOT a provider limit: the provider only bounds the whole transcript.
MODEL_TOOL_MESSAGE_TRIGGER_BYTES = 16 * 1024
# Headroom under the provider's transcript bound for JSON string escaping and framing.
MODEL_TRANSCRIPT_RESERVE_BYTES = 10 * 1024
EXPERIMENT_NOT_SELECTED = "EXPERIMENT_NOT_SELECTED"
EXPERIMENT_NOT_PUBLISHED = "EXPERIMENT_NOT_PUBLISHED"
_PROMPT_EXPERIMENT_ID = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{24}(?![0-9a-fA-F])")
_PROMPT_NAMED_EXPERIMENT_ID = re.compile(
    r"(?i:experiment)[\s:#]*(?<![0-9a-fA-F])([0-9a-fA-F]{24})(?![0-9a-fA-F])"
)
_NOT_SELECTED_ID_PLACEHOLDER = "<24-hex id>"
_EXPERIMENT_ID = re.compile(r"[a-f0-9]{24}")
_MODEL_TRUNCATION_NOTE = (
    "Result truncated for the model: the full result is stored server-side and Python renders "
    "all facts. Do not request more data; return the final JSON plan."
)
# (identifier-prefix items, string characters, inline-value bytes, top-level fields)
_DIGEST_LEVELS = (
    (16, 160, 512, 64),
    (8, 96, 256, 48),
    (4, 48, 128, 32),
    (2, 24, 0, 16),
    (0, 16, 0, 8),
)
_EXPLICIT_EXPERIMENT_SELECTION = re.compile(
    r"[ \t]*(?:please[ \t]+)?(?:read|show|inspect|summari[sz]e|compare|analy[sz]e)"
    r"[ \t]+(?:(?:the[ \t]+)?results?[ \t]+of[ \t]+)?"
    r"(?:published[ \t]+)?experiment(?:[ \t]+(?:id|#))?"
    r"[ \t]*[:=]?[ \t]*([a-f0-9]{24})[.!?]?[ \t]*",
    re.IGNORECASE,
)


def _literal_choices(values) -> str:
    return "(?:" + "|".join(re.escape(str(value)) for value in sorted(values)) + ")"


_READ_CONDITION_KEY = re.compile(
    rf"{_literal_choices(APPROVED_PREDICTORS)}__"
    rf"{_literal_choices(APPROVED_SCENARIOS | frozenset({'mcar_matched_history'}))}__"
    rf"b{_literal_choices(APPROVED_BUDGETS)}__{_literal_choices(APPROVED_CALIBRATORS)}",
    re.ASCII,
)
_EXPLICIT_BOUNDED_READ_SELECTION = re.compile(
    rf"(?i:read)[ \t]+experiment[ \t]+(?P<experiment_id>[a-f0-9]{{24}})"
    rf"[ \t]+condition[ \t]+(?P<condition_key>{_READ_CONDITION_KEY.pattern})",
    re.ASCII,
)
_EXPLICIT_BOUNDED_COMPARE_SELECTION = re.compile(
    rf"(?i:compare)[ \t]+experiment[ \t]+(?P<experiment_id>[a-f0-9]{{24}})"
    rf"[ \t]+calibrators[ \t]+predictor[ \t]+(?P<predictor>{_literal_choices(APPROVED_PREDICTORS)})"
    rf"[ \t]+scenario[ \t]+(?P<scenario>{_literal_choices(APPROVED_SCENARIOS)})"
    rf"[ \t]+budget[ \t]+(?P<budget>{_literal_choices(APPROVED_BUDGETS)})",
    re.ASCII,
)


def _selected_experiment_id(prompt: str) -> str | None:
    """Extract only a full standard or closed, typed bounded selection command."""
    if not isinstance(prompt, str):
        return None
    for pattern in (
        _EXPLICIT_BOUNDED_READ_SELECTION,
        _EXPLICIT_BOUNDED_COMPARE_SELECTION,
        _EXPLICIT_EXPERIMENT_SELECTION,
    ):
        match = pattern.fullmatch(prompt)
        if match is not None:
            return match.groupdict().get("experiment_id") or match.group(1)
    return None


def _utf8_len(text: str) -> int:
    return len(text.encode("utf-8", "replace"))


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "\u2026"


def _clip_key(key: Any, limit: int = 64) -> str:
    """Clip a key for the digest; a clipped key gets a short hash so clipped keys stay distinct."""
    text = str(key)
    if len(text) <= limit:
        return text
    return text[: limit - 9] + "~" + hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:8]


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, bool, int, float))


def _digest_scalar(value: Any, string_limit: int) -> Any:
    if isinstance(value, str):
        return _clip(value, string_limit)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _inline_value(value: Any, limit: int) -> tuple[bool, Any]:
    """Return a canonical copy of a small container, or (False, None)."""
    if limit <= 0:
        return False, None
    try:
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
        )
    except (TypeError, ValueError, RecursionError):
        return False, None
    if _utf8_len(encoded) > limit:
        return False, None
    try:
        return True, json.loads(encoded)
    except (ValueError, RecursionError):
        return False, None


def _digest_container(value: Any, prefix: int, string_limit: int) -> dict[str, Any]:
    if isinstance(value, dict):
        keys = sorted(value, key=str)
        digest: dict[str, Any] = {"item_count": len(keys)}
        head = keys[:prefix]
        ids = {
            _clip_key(key): _clip(value[key]["condition_id"], 64)
            for key in head
            if isinstance(value[key], dict) and isinstance(value[key].get("condition_id"), str)
        }
        if ids:
            digest["condition_ids_prefix"] = ids
        elif head:
            digest["keys_prefix"] = [_clip_key(key) for key in head]
        return digest
    digest = {"list_length": len(value)}
    head = value[:prefix]
    ids = [
        _clip(item["condition_id"], 64) for item in head
        if isinstance(item, dict) and isinstance(item.get("condition_id"), str)
    ]
    keys = [
        _clip(item["condition_key"], 64) for item in head
        if isinstance(item, dict) and isinstance(item.get("condition_key"), str)
    ]
    scalars = [_digest_scalar(item, string_limit) for item in head if _is_scalar(item)]
    if ids:
        digest["condition_ids_prefix"] = ids
    if keys:
        digest["condition_keys_prefix"] = keys
    if scalars:
        digest["first_items"] = scalars
    return digest


def _digest_data(data: Any, level: int) -> Any:
    """Compact, order-independent digest of one tool result's data."""
    if data is None:
        return None
    prefix, string_limit, inline_limit, max_fields = _DIGEST_LEVELS[level]
    if not isinstance(data, dict):
        return {"value_type": type(data).__name__}
    keys = sorted(data, key=str)
    ordered = [k for k in keys if _is_scalar(data[k])] + [k for k in keys if not _is_scalar(data[k])]
    fields: dict[str, Any] = {}
    for key in ordered[:max_fields]:
        value = data[key]
        name = _clip_key(key)
        if _is_scalar(value):
            fields[name] = _digest_scalar(value, string_limit)
            continue
        if isinstance(value, (dict, list)):
            inline, canonical = _inline_value(value, inline_limit)
            fields[name] = canonical if inline else _digest_container(value, prefix, string_limit)
        else:
            fields[name] = None
    digest: dict[str, Any] = {"key_count": len(keys), "fields": fields}
    omitted = ordered[max_fields:]
    if omitted:
        digest["omitted_key_count"] = len(omitted)
        if prefix:
            digest["omitted_keys"] = [_clip_key(key) for key in omitted[:prefix]]
    return digest


def _bounded_error(error: Any) -> Any:
    if isinstance(error, str):
        return _clip(error, 300)
    if isinstance(error, dict):
        return {
            _clip_key(key, 32): _clip(value, 256) if isinstance(value, str) else None
            for key, value in sorted(error.items(), key=lambda item: str(item[0]))[:4]
        }
    return None


def project_tool_result_for_model(
    result_data: dict[str, Any], max_bytes: int = MAX_MODEL_TOOL_MESSAGE_BYTES,
) -> str:
    """Return the model-facing tool message content, never more than 6 KB of UTF-8.

    Results that already fit are serialized exactly as before. Larger results keep
    their identity, status, error and side-effect fields but replace ``data`` by a
    deterministic digest. The caller stores the full result separately, and Python
    renders every empirical fact from that stored copy.
    """
    limit = max(MIN_MODEL_TOOL_MESSAGE_BYTES, min(int(max_bytes), MAX_MODEL_TOOL_MESSAGE_BYTES))
    encoded = json.dumps(result_data, ensure_ascii=False)
    if _utf8_len(encoded) <= limit:
        return encoded

    def message(data: Any) -> str:
        tool_name = result_data.get("tool_name")
        job_id = result_data.get("job_id")
        return json.dumps({
            "tool_name": _clip(tool_name, 64) if isinstance(tool_name, str) else None,
            "tool_call_id": result_data.get("tool_call_id"),
            "status": result_data.get("status"),
            "data": data,
            "error": _bounded_error(result_data.get("error")),
            "is_side_effect": bool(result_data.get("is_side_effect", False)),
            "job_id": _clip(job_id, 128) if isinstance(job_id, str) else None,
            "data_truncated": True,
            "note": _MODEL_TRUNCATION_NOTE,
        }, ensure_ascii=False, allow_nan=False)

    raw_data = result_data.get("data")
    for level in range(len(_DIGEST_LEVELS)):
        candidate = message(_digest_data(raw_data, level))
        if _utf8_len(candidate) <= limit:
            return candidate
    candidate = message(None if raw_data is None else {"omitted": True})
    if _utf8_len(candidate) <= limit:
        return candidate
    return json.dumps({
        "tool_call_id": result_data.get("tool_call_id"), "status": result_data.get("status"),
        "data_truncated": True,
    }, ensure_ascii=False)


def _same_canonical_arguments(left: dict[str, Any], right: dict[str, Any]) -> bool:
    try:
        return json.dumps(
            left, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ) == json.dumps(
            right, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        )
    except (TypeError, ValueError, RecursionError):
        return False


def _sanitize_trace_arguments(args: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in args.items():
        name = str(key)[:64]
        if isinstance(value, str):
            safe[name] = value if len(value) <= 256 else value[:128] + "…[bounded]"
        elif isinstance(value, (dict, list)):
            try:
                encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
            except (TypeError, ValueError, RecursionError):
                safe[name] = "[rejected]"
            else:
                safe[name] = value if len(encoded.encode("utf-8")) <= 1024 else "[bounded]"
        elif value is None or type(value) in (bool, int, float):
            safe[name] = value
        else:
            safe[name] = "[rejected]"
    return safe


def _not_selected_message(experiment_id: str | None) -> str:
    reference = experiment_id if experiment_id and _EXPERIMENT_ID.fullmatch(experiment_id) else _NOT_SELECTED_ID_PLACEHOLDER
    return (
        "Saved experiments are readable only through an exact command. "
        f"Ask exactly: Summarize experiment {reference}. "
        "You can also use the suggestion buttons under the saved result."
    )


def _not_published_message(experiment_id: str) -> str:
    return (
        f"Experiment {experiment_id} is not a published result on this server. "
        "Open a saved result and use its buttons."
    )


def _prompt_experiment_id(prompt: str) -> str | None:
    """The experiment id named in the user's own prompt; never a model-chosen id.

    Condition ids are also 24-hex, so a token right after the word "experiment" wins. Without
    one, a lone 24-hex token is used; several ambiguous tokens yield None (guidance omits an id).
    """
    if not isinstance(prompt, str):
        return None
    named = _PROMPT_NAMED_EXPERIMENT_ID.search(prompt)
    if named:
        return named.group(1).lower()
    tokens = {m.group(0).lower() for m in _PROMPT_EXPERIMENT_ID.finditer(prompt)}
    return next(iter(tokens)) if len(tokens) == 1 else None


def _error_code(error: Any) -> str | None:
    if isinstance(error, dict):
        code = error.get("code")
        return code if isinstance(code, str) else None
    if isinstance(error, str):
        return error.split(":", 1)[0].strip() or None
    return None


def _safe_public_error(error: Any) -> str | dict[str, Any] | None:
    if error is None:
        return None
    if isinstance(error, str):
        return safe_tool_error(error) or "REQUEST_FAILED: The request failed."
    if isinstance(error, dict):
        code = error.get("code")
        if not isinstance(code, str) or not re.fullmatch(r"[A-Z0-9_]{1,48}", code):
            code = "REQUEST_FAILED"
        message = error.get("message")
        text = safe_tool_error(f"{code}: {message}") if isinstance(message, str) else None
        if not text or not text.startswith(code + ":"):
            text = f"{code}: The operation failed."
        return {"code": code, "message": text.split(":", 1)[1].strip()[:256]}
    return {"code": "REQUEST_FAILED", "message": "The operation failed."}


def _terminal_request_outcome(final: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    final_status = final.get("status") if isinstance(final, dict) else None
    status = final_status if final_status in ("FAILED", "CANCELLED") else "COMPLETED"
    if isinstance(final, dict):
        final["status"] = status
    error = None if status == "COMPLETED" else {
        "code": status,
        "message": final.get("summary", "The request did not complete successfully."),
    }
    return status, error


def format_agent_response(
    req: AgentRequestRecord, store: AgentStore, executions: list[Any] | None = None
) -> dict[str, Any]:
    rows = executions if executions is not None else store.list_tool_executions(req.id)
    trace = [
        ToolTraceEntry(
            ordinal=e.ordinal, tool_name=e.tool_name, tool_call_id=e.tool_call_id,
            arguments=_sanitize_trace_arguments(e.arguments), status=e.status,
            result=e.result, error=_safe_public_error(e.result.get("error")) if e.result else None,
            job_id=e.job_id,
        ).model_dump(mode="json")
        for e in rows
    ]
    return {
        "request_id": req.id, "session_id": req.session_id, "status": req.status,
        "prompt": req.prompt, "turn_count": req.turn_count, "call_count": req.call_count,
        "repair_count": req.repair_count, "active_job_id": req.active_job_id,
        "active_tool_call_id": req.active_tool_call_id,
        "resume_nonce": req.active_nonce if req.status == "WAITING_FOR_JOB" else None,
        "tool_trace": trace, "evidence_refs": req.evidence_refs,
        "final_response": req.final_response, "error": _safe_public_error(req.error) if req.error else None,
        "created_at": req.created_at, "updated_at": req.updated_at,
    }


class AgentController:
    """Run and resume persisted provider decisions under a request lease."""

    def __init__(
        self, engine: Engine, settings: Settings, store: AgentStore,
        registry: ToolRegistry, provider: ProviderClient, session_token: str | None = None,
    ) -> None:
        self.engine = engine
        self.settings = settings
        self.store = store
        self.registry = registry
        self.provider = provider
        self.session_token = session_token
        self.queue = JobQueue(engine)

    def _response_factory(self, req, executions, extra=None):
        response = format_agent_response(req, self.store, executions)
        if extra:
            response.update(extra)
        return response

    def _build_tool_trace(self, request_id: str) -> list[ToolTraceEntry]:
        return [
            ToolTraceEntry(
                ordinal=e.ordinal, tool_name=e.tool_name, tool_call_id=e.tool_call_id,
                arguments=_sanitize_trace_arguments(e.arguments), status=e.status,
                result=e.result, error=_safe_public_error(e.result.get("error")) if e.result else None,
                job_id=e.job_id,
            )
            for e in self.store.list_tool_executions(request_id)
        ]

    def _get_required_request(self, request_id: str) -> AgentRequestRecord:
        req = self.store.get_request(request_id)
        if not req:
            raise RuntimeError(f"Request '{request_id}' not found")
        return req

    def _bind_selected_publications(self, req, generation, worker_id):
        selected = _selected_experiment_id(req.prompt)
        if selected is None:
            return req
        selected = selected.lower()
        repository = ExperimentRepository(self.engine)
        if repository.get_published(selected) is None:
            return req
        refs = list(dict.fromkeys([*req.evidence_refs, selected]))
        if refs == req.evidence_refs:
            return req
        updated = self.store.update_request(
            req.id, generation, evidence_refs=refs, worker_id=worker_id,
        )
        if not updated:
            raise LeaseLostError("Request lease changed before selected evidence was bound")
        return self._get_required_request(req.id)

    def _normalize_saved_decision(self, req, generation, worker_id):
        decision = req.accepted_decision
        if decision is None:
            return req
        if not isinstance(decision, dict) or not isinstance(decision.get("tool_calls", []), list):
            raise ValueError("Saved accepted decision has an invalid shape")

        normalized = dict(decision)
        calls = []
        changed = False
        for saved_call in decision.get("tool_calls", []):
            if not isinstance(saved_call, dict):
                raise ValueError("Saved accepted tool call has an invalid shape")
            call = dict(saved_call)
            arguments = call.get("arguments")
            if isinstance(arguments, str):
                try:
                    if len(arguments.encode("utf-8")) > MAX_PROVIDER_ARGUMENT_BYTES:
                        raise ValueError("Saved tool arguments exceeded the bounded decision limit")
                    parsed = json.loads(
                        arguments,
                        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
                    )
                    if not isinstance(parsed, dict):
                        raise ValueError("Saved tool arguments must be a JSON object")
                    encoded = json.dumps(parsed, ensure_ascii=False, allow_nan=False)
                    if len(encoded.encode("utf-8")) > MAX_PROVIDER_ARGUMENT_BYTES:
                        raise ValueError("Saved tool arguments exceeded the bounded decision limit")
                except (json.JSONDecodeError, UnicodeEncodeError, RecursionError) as exc:
                    raise ValueError("Saved tool arguments are not valid bounded JSON") from exc
                name = call.get("name")
                if not isinstance(name, str) or not self.registry.prepare_arguments(name, parsed).ok:
                    raise ValueError("Saved legacy tool arguments failed request validation")
                call["arguments"] = parsed
                changed = True
            elif not isinstance(arguments, dict):
                raise ValueError("Saved accepted tool arguments have an invalid shape")
            calls.append(call)

        if not changed:
            return req
        normalized["tool_calls"] = calls
        updated = self.store.update_request(
            req.id, generation, accepted_decision=normalized, worker_id=worker_id,
        )
        if not updated:
            raise LeaseLostError("Request lease changed while normalizing a saved tool decision")
        return self._get_required_request(req.id)

    def _semantic_retry_signature(self, name, arguments, ledger, executions):
        signature = None
        if name == "calculate_decision_loss":
            fp_cost, fn_cost = arguments.get("fp_cost"), arguments.get("fn_cost")
            numeric = all(
                isinstance(value, (int, float)) and type(value) is not bool
                and math.isfinite(float(value))
                for value in (fp_cost, fn_cost)
            )
            if numeric and (float(fp_cost), float(fn_cost)) not in SUPPORTED_COST_PAIRS:
                signature = normalized_repair_signature(name, AgentErrorCode.UNSUPPORTED_COST_PAIR)

        if signature is None:
            for previous in executions:
                if (
                    previous.tool_name != name
                    or not _same_canonical_arguments(previous.arguments, arguments)
                    or previous.status != "error"
                ):
                    continue
                error = (previous.result or {}).get("error")
                if isinstance(error, dict):
                    code = error.get("code")
                    if isinstance(code, str) and code not in {
                        AgentErrorCode.REPAIR_BUDGET_EXCEEDED, AgentErrorCode.BUDGET_EXCEEDED,
                    }:
                        signature = normalized_repair_signature(name, code)
                elif isinstance(error, str):
                    candidate = compute_repair_signature(name, error)
                    if not candidate.endswith(":REPAIR_BUDGET_EXCEEDED:") and not candidate.endswith(":BUDGET_EXCEEDED:"):
                        signature = candidate
                if signature:
                    break

        if signature and signature not in ledger:
            # Old persisted traces may predate the durable repair-ledger reservation.
            if any(
                previous.tool_name == name and _same_canonical_arguments(previous.arguments, arguments)
                and previous.status == "error"
                for previous in executions
            ):
                ledger[signature] = 0
        return signature

    def _reserved_pending_repair(self, name, signature, ordinal, ledger, executions):
        if signature:
            candidates = [signature]
        else:
            prefix = name.lower() + ":"
            candidates = [
                key for key, attempts in ledger.items()
                if key.startswith(prefix) and int(attempts) >= MAX_REPAIRS_PER_SIGNATURE
            ]

        matches = []
        for candidate in candidates:
            if int(ledger.get(candidate, -1)) < MAX_REPAIRS_PER_SIGNATURE:
                continue
            failures = []
            for execution in executions:
                if execution.ordinal >= ordinal or execution.tool_name != name or execution.status != "error":
                    continue
                error = (execution.result or {}).get("error")
                if isinstance(error, dict):
                    code = error.get("code")
                    if isinstance(code, str) and code not in {
                        AgentErrorCode.REPAIR_BUDGET_EXCEEDED, AgentErrorCode.BUDGET_EXCEEDED,
                    }:
                        failed_signature = normalized_repair_signature(name, code)
                    else:
                        failed_signature = None
                elif isinstance(error, str):
                    failed_signature = compute_repair_signature(name, error)
                    if (
                        failed_signature.endswith(":REPAIR_BUDGET_EXCEEDED:")
                        or failed_signature.endswith(":BUDGET_EXCEEDED:")
                    ):
                        failed_signature = None
                else:
                    failed_signature = None
                if failed_signature == candidate:
                    failures.append(execution)

            if not failures:
                continue
            first_failure = min(failures, key=lambda execution: execution.ordinal)
            intervening_tool_calls = any(
                first_failure.ordinal < execution.ordinal < ordinal
                and execution.tool_name == name
                for execution in executions
            )
            owns_reservation = len(failures) == 1 and not intervening_tool_calls
            matches.append((candidate, owns_reservation))

        owners = [match for match in matches if match[1]]
        if len(owners) == 1:
            # Earlier spent signatures cannot invalidate this exact pending intent's
            # sole reservation; ambiguous ownership still fails closed below.
            return owners[0][0], True, True
        if len(matches) == 1:
            return matches[0][0], matches[0][1], True
        return None, False, bool(matches)

    def _normalize_decision(self, response, prior_call_ids: set[str] | None = None):
        provider_calls = list(response.tool_calls or [])
        if len(provider_calls) > MAX_ACCEPTED_TOOL_CALLS:
            raise ValueError("Provider returned more calls than the bounded decision limit")
        if response.content is not None and len(response.content.encode("utf-8")) > MAX_PROVIDER_CONTENT_BYTES:
            raise ValueError("Provider content exceeded the bounded decision limit")
        calls, assistant_calls = [], []
        seen_call_ids: set[str] = set(prior_call_ids or ())
        for tc in provider_calls:
            call_id, name = tc.id, tc.function.name
            if safe_tool_call_id(call_id) is None:
                raise ValueError("Provider returned an invalid tool call identifier")
            if call_id in seen_call_ids:
                raise ValueError("Provider reused a tool call identifier within this request")
            seen_call_ids.add(call_id)
            if not isinstance(name, str) or not 1 <= len(name.encode("utf-8")) <= 64:
                raise ValueError("Provider returned an invalid tool name")
            raw_arguments = tc.function.arguments
            if len(raw_arguments.encode("utf-8")) > MAX_PROVIDER_ARGUMENT_BYTES:
                raise ValueError("Provider tool arguments exceeded the bounded decision limit")
            prepared = self.registry.prepare_arguments(name, raw_arguments)
            arguments = safe_arguments_for_storage(prepared)
            signature = rejection = None
            if not prepared.ok:
                signature = normalized_repair_signature(
                    name, prepared.rejection_code or AgentErrorCode.INVALID_ARGUMENTS,
                    prepared.rejected_fields[0] if prepared.rejected_fields else "",
                )
                rejection = prepared.safe_error or "INVALID_ARGUMENTS: Arguments were rejected."
            calls.append({
                "id": call_id, "name": name, "arguments": arguments,
                "rejection": rejection, "repair_signature": signature,
            })
            assistant_calls.append({
                "id": call_id, "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
            })
        decision = {"content": response.content, "tool_calls": calls}
        assistant = {"role": "assistant", "content": response.content}
        if assistant_calls:
            assistant["tool_calls"] = assistant_calls
        if len(json.dumps(decision, ensure_ascii=False).encode("utf-8")) > MAX_PROVIDER_DECISION_BYTES:
            raise ValueError("Provider decision exceeded the bounded storage limit")
        return decision, assistant

    def _final_answer(self, req: AgentRequestRecord, content: str | None = None) -> dict[str, Any]:
        executions = self.store.list_tool_executions(req.id)
        adverse = [e for e in executions if e.status in ("error", "failed", "cancelled")]
        if adverse:
            outcomes = [{
                "tool_call_id": e.tool_call_id, "tool_name": e.tool_name,
                "status": e.status, "job_id": e.job_id,
                "error": _safe_public_error((e.result or {}).get("error")),
            } for e in adverse]
            return {
                "status": "FAILED" if any(e["status"] != "cancelled" for e in outcomes) else "CANCELLED",
                "summary": "One or more requested operations failed or were cancelled.",
                "outcomes": outcomes, "evidence_refs": req.evidence_refs,
            }
        return ResultRenderer.ground_assistant_message(
            assistant_text=content,
            tool_trace=[e.model_dump(mode="json") for e in self._build_tool_trace(req.id)],
            evidence_refs=req.evidence_refs, prompt=req.prompt,
        )

    @staticmethod
    def _messages_for_provider(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Build the model-facing copy of the stored transcript, deterministically each turn.

        The stored transcript keeps every full tool result. A transcript whose tool messages
        are all within MODEL_TOOL_MESSAGE_TRIGGER_BYTES and that is within the provider's
        MAX_TRANSCRIPT_BYTES is returned byte-identical. Otherwise a tool message over the
        trigger, or one that would push the transcript past that bound less a reserve, becomes
        a digest, and, only if the copy is still too large, assistant prose is clipped.

        When a projection runs, the persisted transcript prefix differs from the dispatched
        provider copy, so an auditor recomputing the input fingerprint must apply this (pure,
        deterministic) function to the stored prefix before hashing.
        """
        def size(value: Any) -> int:
            return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8", "replace"))

        def over_trigger(message: Any) -> bool:
            content = message.get("content") if isinstance(message, dict) else None
            return (
                isinstance(message, dict) and message.get("role") == "tool"
                and isinstance(content, str) and _utf8_len(content) > MODEL_TOOL_MESSAGE_TRIGGER_BYTES
            )

        if size(messages) <= MAX_PROVIDER_TRANSCRIPT_BYTES and not any(over_trigger(m) for m in messages):
            return list(messages)
        budget = MAX_PROVIDER_TRANSCRIPT_BYTES - MODEL_TRANSCRIPT_RESERVE_BYTES
        out: list[dict[str, Any]] = []
        used = 0
        for message in messages:
            if isinstance(message, dict) and message.get("role") == "tool" and isinstance(message.get("content"), str):
                # Only results that the provider would reject are projected; the model then sees a
                # deterministic digest, the stored transcript keeps the full result, and Python
                # renders from the stored execution.
                if over_trigger(message) or used + size(message) > budget:
                    try:
                        parsed = json.loads(message["content"])
                    except (ValueError, RecursionError):
                        parsed = None
                    if isinstance(parsed, dict):
                        message = {**message, "content": project_tool_result_for_model(parsed, max_bytes=budget - used)}
            out.append(message)
            used += size(message) + 1
        # Safety net: assistant prose can be up to 16 KB per turn; clip it (oldest first) only
        # while the provider copy is still over the transcript bound.
        for index, message in enumerate(out):
            if size(out) <= MAX_PROVIDER_TRANSCRIPT_BYTES:
                break
            content = message.get("content") if isinstance(message, dict) else None
            if isinstance(message, dict) and message.get("role") == "assistant" and isinstance(content, str) and len(content) > 256:
                out[index] = {**message, "content": content[:256] + "\u2026"}
        return out

    def _unselected_experiment_attempts(self, req) -> list[Any]:
        """Executions that named a saved experiment the user never selected.

        Empty when evidence is bound or when the prompt is an explicit run command: a run
        command legitimately proceeds past a speculative read.
        """
        if req.evidence_refs or authorized_execution_presets(req.prompt):
            return []
        return [
            execution for execution in self.store.list_tool_executions(req.id)
            if _error_code((execution.result or {}).get("error"))
            == AgentErrorCode.UNAUTHORIZED_EXPERIMENT_REFERENCE
        ]

    def _finish_experiment_not_selected(self, req, generation, worker_id, nonce):
        selected = _selected_experiment_id(req.prompt)
        if selected is not None:
            guidance = {
                "code": EXPERIMENT_NOT_PUBLISHED,
                "message": _not_published_message(selected.lower()),
            }
        else:
            guidance = {
                "code": EXPERIMENT_NOT_SELECTED,
                "message": _not_selected_message(_prompt_experiment_id(req.prompt)),
            }
        # Failed or cancelled operations keep their terminal status; the guidance rides along.
        # Otherwise keep the renderer's response shape (empty claims, typed tool errors,
        # disclaimer). Provider prose is never used, and the id comes only from the prompt.
        response = self._final_answer(req)
        if response.get("status") in ("FAILED", "CANCELLED"):
            response["guidance"] = guidance
            status, error = _terminal_request_outcome(response)
        else:
            response.update({
                "status": "COMPLETED",
                "title": "Experiment not published on this server"
                if guidance["code"] == EXPERIMENT_NOT_PUBLISHED else "Saved experiment not selected",
                "summary": guidance["message"], "provider_narrative": guidance["message"],
                "claims": [], "guidance": guidance, "evidence_refs": [],
            })
            status, error = "COMPLETED", None
        try:
            _, _, updated = self.store.finish_request(
                req.id, generation, worker_id, status, response, error,
                nonce, self._response_factory,
            )
            return updated
        except LeaseLostError:
            return self._get_required_request(req.id)

    def _finish_budget(self, req, generation, worker_id, nonce):
        response = self._final_answer(req)
        response["budget_limit_reached"] = (
            f"The bounded request limit was reached ({req.turn_count}/{MAX_TURNS} turns, "
            f"{req.call_count}/{MAX_TOOL_CALLS} calls)."
        )
        status, error = _terminal_request_outcome(response)
        try:
            _, _, updated = self.store.finish_request(
                req.id, generation, worker_id, status, response, error,
                nonce, self._response_factory,
            )
            return updated
        except LeaseLostError:
            return self._get_required_request(req.id)

    async def execute_request(self, request_id: str, worker_id: str) -> AgentRequestRecord:
        """Claim a new request or recover its saved decision without another provider turn."""
        current = self.store.get_request(request_id)
        if not current:
            raise ValueError(f"Request '{request_id}' not found")
        current = self.store.bind_legacy_request_authority(
            request_id, current.session_id, self.session_token,
        ) or current
        if not self.store.verify_request_authority(request_id, self.session_token):
            return current
        if current.status in ("WAITING_FOR_JOB", "COMPLETED", "FAILED", "CANCELLED"):
            return current
        claimed, req = self.store.claim_lease(request_id, worker_id, lease_seconds=120)
        if not claimed or not req:
            return self.store.get_request(request_id) or current
        continuation_nonce = (
            req.active_nonce
            if req.active_nonce is not None
            and req.active_nonce_generation is not None
            and req.active_nonce_generation <= req.generation
            else None
        )
        return await self._run_owned_request(
            req, req.generation, worker_id, continuation_nonce,
        )

    async def _run_owned_request(self, initial, generation, worker_id, continuation_nonce):
        request_id = initial.id
        try:
            while True:
                has_lease, req = self.store.verify_lease(request_id, generation, worker_id)
                if not has_lease or not req:
                    return req or self._get_required_request(request_id)

                req = self._bind_selected_publications(req, generation, worker_id)
                req = self._normalize_saved_decision(req, generation, worker_id)

                decision = req.accepted_decision
                if decision is None:
                    # A completed decision hit an unselected saved experiment and the request
                    # binds no evidence: no further provider turn can legitimately read it.
                    attempts = self._unselected_experiment_attempts(req)
                    if attempts:
                        return self._finish_experiment_not_selected(
                            req, generation, worker_id, continuation_nonce,
                        )
                    if req.turn_count >= MAX_TURNS or req.call_count >= MAX_TOOL_CALLS:
                        return self._finish_budget(req, generation, worker_id, continuation_nonce)
                    messages = list(req.messages)
                    if not messages or messages[0].get("role") != "system":
                        messages = [build_system_message(), {"role": "user", "content": req.prompt}]
                    elif not any(m.get("role") == "user" for m in messages):
                        messages.append({"role": "user", "content": req.prompt})
                    self.store.reserve_provider_turn(
                        request_id, generation, worker_id, self.session_token or "", req.turn_count,
                    )
                    current = self._get_required_request(request_id)
                    if not self.store.renew_lease(request_id, generation, worker_id, lease_seconds=120):
                        return self._get_required_request(request_id)
                    try:
                        response = await self.provider.chat(
                            messages=self._messages_for_provider(messages),
                            tools=self.registry.get_openai_tool_definitions(),
                        )
                    except ProviderDisabledError as err:
                        return self._finish_provider_error(
                            request_id, generation, worker_id, continuation_nonce, err
                        )
                    except ProviderError as err:
                        return self._finish_provider_error(
                            request_id, generation, worker_id, continuation_nonce, err
                        )
                    has_lease, current = self.store.verify_lease(request_id, generation, worker_id)
                    if not has_lease or not current:
                        return current or self._get_required_request(request_id)
                    prior_call_ids = {
                        execution.tool_call_id
                        for execution in self.store.list_tool_executions(request_id)
                    }
                    for message in current.messages:
                        if not isinstance(message, dict) or not isinstance(message.get("tool_calls"), list):
                            continue
                        for saved_call in message["tool_calls"]:
                            if isinstance(saved_call, dict) and isinstance(saved_call.get("id"), str):
                                prior_call_ids.add(saved_call["id"])
                    decision, assistant_message = self._normalize_decision(
                        response, prior_call_ids=prior_call_ids,
                    )
                    decision["first_ordinal"] = current.call_count + 1
                    messages.append(assistant_message)
                    self.store.checkpoint_decision(
                        request_id, generation, worker_id, self.session_token or "",
                        decision, messages, current.turn_count,
                    )
                    req = self._get_required_request(request_id)
                    decision = req.accepted_decision
                    if decision is None:
                        raise RuntimeError("Accepted provider decision was not persisted")

                calls = decision.get("tool_calls", [])
                if not calls:
                    final = self._final_answer(req, decision.get("content"))
                    terminal, error = _terminal_request_outcome(final)
                    try:
                        _, _, updated = self.store.finish_request(
                            request_id, generation, worker_id, terminal, final, error,
                            continuation_nonce, self._response_factory,
                        )
                        return updated
                    except LeaseLostError:
                        return self._get_required_request(request_id)

                if req.pending_cursor >= len(calls):
                    self.store.advance_tool_cursor(
                        request_id, generation, worker_id, self.session_token or "",
                        req.messages, 0, complete_decision=True,
                    )
                    continue

                paused = self._dispatch_decision(
                    req, generation, worker_id, continuation_nonce
                )
                if paused is not None:
                    return paused

        except LeaseLostError:
            return self._get_required_request(request_id)
        except RequestAuthorityError as err:
            req = self._get_required_request(request_id)
            try:
                _, _, updated = self.store.finish_request(
                    request_id, generation, worker_id, "FAILED",
                    {"status": "FAILED", "summary": "The request session authority is no longer active."},
                    {"code": AgentErrorCode.UNAUTHORIZED_SESSION, "message": str(err)},
                    continuation_nonce, self._response_factory,
                )
                return updated
            except Exception:
                return req
        except Exception as err:
            logger.exception("Agent request %s failed", request_id)
            req = self._get_required_request(request_id)
            try:
                _, _, updated = self.store.finish_request(
                    request_id, generation, worker_id, "FAILED",
                    {"status": "FAILED", "summary": "The request could not be completed safely."},
                    {"code": AgentErrorCode.REQUEST_FAILED,
                     "message": safe_tool_error(str(err)) or "Request failed."},
                    continuation_nonce, self._response_factory,
                )
                return updated
            except Exception:
                return req

    def _finish_provider_error(self, request_id, generation, worker_id, nonce, err):
        code = err.code
        message = safe_tool_error(err.message) or f"{code}: Provider request failed."
        final = {"status": "FAILED", "summary": "The provider request failed safely."}
        try:
            _, _, updated = self.store.finish_request(
                request_id, generation, worker_id, "FAILED", final,
                {"code": code, "message": message}, nonce, self._response_factory,
            )
            return updated
        except LeaseLostError:
            return self._get_required_request(request_id)

    def _dispatch_decision(self, req, generation, worker_id, continuation_nonce):
        decision = req.accepted_decision or {}
        calls = decision.get("tool_calls", [])
        cursor = req.pending_cursor
        while cursor < len(calls):
            current = self._get_required_request(req.id)
            has_lease, current = self.store.verify_lease(req.id, generation, worker_id)
            if not has_lease or not current:
                return current or self._get_required_request(req.id)
            decision = current.accepted_decision or decision
            calls = decision.get("tool_calls", [])
            cursor = current.pending_cursor
            if cursor >= len(calls):
                break

            call = calls[cursor]
            name = str(call.get("name") or "unknown")
            call_id = str(call.get("id") or "")
            ordinal = int(decision.get("first_ordinal") or 1) + cursor
            arguments = call.get("arguments") if isinstance(call.get("arguments"), dict) else {}
            executions = self.store.list_tool_executions(req.id)
            existing = next((entry for entry in executions if entry.ordinal == ordinal), None)
            reserved_pending = False
            if existing is not None:
                if (
                    existing.status != "PENDING"
                    or existing.tool_name != name
                    or existing.tool_call_id != call_id
                    or not _same_canonical_arguments(existing.arguments, arguments)
                ):
                    raise IdempotencyConflictError(
                        "Saved ordinal conflicts with the accepted immutable tool intent"
                    )
                reserved_pending = True
            if current.call_count >= MAX_TOOL_CALLS and not reserved_pending:
                overflow = ToolResult(
                    tool_name=name, tool_call_id=call_id, status="error",
                    error=f"{AgentErrorCode.BUDGET_EXCEEDED}: The eight-call request limit was reached.",
                ).model_dump(mode="json")
                messages = list(current.messages)
                if not any(m.get("role") == "tool" and m.get("tool_call_id") == call_id for m in messages):
                    messages.append({
                        "role": "tool", "name": name, "tool_call_id": call_id,
                        "content": json.dumps(overflow, ensure_ascii=False),
                    })
                next_cursor = cursor + 1
                self.store.advance_tool_cursor(
                    req.id, generation, worker_id, self.session_token or "",
                    messages, next_cursor, next_cursor >= len(calls),
                )
                if next_cursor >= len(calls):
                    return None
                continue

            rejection = call.get("rejection")
            signature = call.get("repair_signature")
            ledger = dict(current.repair_ledger)
            repair_count = current.repair_count
            repair_reserved = False

            if not rejection:
                prepared = self.registry.prepare_arguments(name, arguments)
                if not prepared.ok:
                    rejection = prepared.safe_error or "INVALID_ARGUMENTS: Arguments were rejected."
                    signature = normalized_repair_signature(
                        name, prepared.rejection_code or AgentErrorCode.INVALID_ARGUMENTS,
                        prepared.rejected_fields[0] if prepared.rejected_fields else "",
                    )
                    arguments = safe_arguments_for_storage(prepared)

            if not rejection and not signature:
                signature = self._semantic_retry_signature(name, arguments, ledger, executions)

            budget_error = False
            pending_signature, owns_pending_reservation, has_pending_reservation = (
                self._reserved_pending_repair(name, signature, ordinal, ledger, executions)
                if reserved_pending else (None, False, False)
            )
            if pending_signature and not signature:
                signature = pending_signature
            if has_pending_reservation and not owns_pending_reservation:
                budget_error = True
            elif owns_pending_reservation and pending_signature == signature:
                repair_reserved = True
            if signature:
                attempts = int(ledger.get(signature, -1))
                if owns_pending_reservation and pending_signature == signature:
                    pass
                elif attempts >= MAX_REPAIRS_PER_SIGNATURE:
                    budget_error = True
                elif attempts == 0:
                    ledger[signature] = 1
                    repair_count += 1
                    repair_reserved = True
                    if rejection:
                        budget_error = True
            elif not rejection and not budget_error:
                open_signatures = [
                    key for key, count in ledger.items()
                    if count == 0 and key.startswith(name.lower() + ":")
                ]
                if len(open_signatures) == 1:
                    ledger[open_signatures[0]] = 1
                    repair_count += 1
                    repair_reserved = True

            next_count = max(current.call_count, ordinal)
            idempotency_key = f"agent:{req.id}:{ordinal}"
            self.store.record_tool_execution(
                request_id=req.id, ordinal=ordinal, tool_name=name, tool_call_id=call_id,
                arguments=arguments, idempotency_key=idempotency_key, status="PENDING",
                expected_generation=generation, worker_id=worker_id,
                session_token=self.session_token, decision_index=cursor,
                call_count=next_count, repair_ledger=ledger, repair_count=repair_count,
            )

            if budget_error:
                result = ToolResult(
                    tool_name=name, tool_call_id=call_id, status="error",
                    error=f"{AgentErrorCode.REPAIR_BUDGET_EXCEEDED}: One correction for this normalized error was already used.",
                )
            elif rejection:
                result = ToolResult(
                    tool_name=name, tool_call_id=call_id, status="error", error=str(rejection),
                )
            else:
                authorized = set(current.evidence_refs)
                for previous in executions:
                    if previous.status == "success" and previous.result:
                        experiment_id = previous.result.get("experiment_id")
                        if experiment_id:
                            authorized.add(experiment_id)
                context = ToolContext(
                    engine=self.engine, settings=self.settings, session_id=current.session_id,
                    session_token=self.session_token, request_id=req.id, ordinal=ordinal,
                    authorized_experiment_ids=frozenset(authorized),
                    authorized_run_presets=authorized_execution_presets(current.prompt),
                    admit_job=lambda params, i=cursor, o=ordinal, n=name, cid=call_id, key=idempotency_key:
                        self._admit_job(
                            params, req.id, generation, worker_id, continuation_nonce,
                            o, i, n, cid, key, i + 1,
                        ),
                )
                result = self.registry.dispatch(
                    name=name, raw_arguments=json.dumps(arguments, ensure_ascii=False),
                    ctx=context, tool_call_id=call_id,
                )
                latest = self._get_required_request(req.id)
                if latest.status == "WAITING_FOR_JOB":
                    return latest
                has_lease, latest = self.store.verify_lease(req.id, generation, worker_id)
                if not has_lease or not latest:
                    return latest or self._get_required_request(req.id)

            result_data = result.model_dump(mode="json")
            if result_data.get("error") is not None:
                result_data["error"] = _safe_public_error(result_data["error"])
            if result.status == "error":
                if signature:
                    if repair_reserved:
                        result_data["error"] = (
                            f"{AgentErrorCode.REPAIR_BUDGET_EXCEEDED}: The single correction attempt failed."
                        )
                    elif signature not in ledger:
                        ledger[signature] = 0
                else:
                    failed_signature = compute_repair_signature(
                        name, str(result_data.get("error") or "REQUEST_FAILED")
                    )
                    if failed_signature not in ledger:
                        ledger[failed_signature] = 0
            messages = list(current.messages)
            if not any(m.get("role") == "tool" and m.get("tool_call_id") == call_id for m in messages):
                messages.append({
                    "role": "tool", "name": name, "tool_call_id": call_id,
                    "content": json.dumps(result_data, ensure_ascii=False),
                })
            next_cursor = cursor + 1
            self.store.commit_tool_step(
                request_id=req.id, ordinal=ordinal, expected_generation=generation,
                worker_id=worker_id, session_token=self.session_token or "",
                status=result.status, result=result_data, messages=messages,
                pending_cursor=next_cursor, repair_ledger=ledger,
                repair_count=repair_count, complete_decision=next_cursor >= len(calls),
            )
            if next_cursor >= len(calls):
                return None
        return None

    def _admit_job(
        self, params, request_id, generation, worker_id, continuation_nonce,
        ordinal, decision_index, tool_name, tool_call_id, idempotency_key, next_cursor,
    ):
        if not self.session_token:
            raise RequestAuthorityError("Fenced admission requires verified session authority")
        with self.queue.admission_transaction() as conn:
            return self.store.admit_agent_job(
                conn=conn, queue=self.queue, request_params=params,
                request_id=request_id, expected_generation=generation, worker_id=worker_id,
                session_token=self.session_token, ordinal=ordinal, decision_index=decision_index,
                tool_name=tool_name, tool_call_id=tool_call_id,
                idempotency_key=idempotency_key, next_cursor=next_cursor,
                continuation_nonce=continuation_nonce, response_factory=self._response_factory,
            )

    async def resume_request(self, request_id: str, nonce: str, worker_id: str) -> tuple[int, dict[str, Any]]:
        """Resume or replay only a nonce the server issued and durably bound."""
        if not self.session_token:
            return 401, {"error": {"code": "MISSING_SESSION_CREDENTIALS", "message": "Session authority is required."}}
        current = self.store.get_request(request_id)
        if not current:
            return 404, {"error": {"code": "REQUEST_NOT_FOUND", "message": "Request not found."}}
        if not self.store.bind_legacy_request_authority(
            request_id, current.session_id, self.session_token,
        ):
            return 403, {"error": {"code": "SESSION_AUTHORITY_CHANGED", "message": "Request authority is no longer valid."}}
        try:
            state, req, receipt = self.store.claim_continuation(
                request_id, nonce, worker_id, self.session_token, lease_seconds=120
            )
        except RequestAuthorityError:
            return 403, {"error": {"code": "SESSION_AUTHORITY_CHANGED", "message": "Request authority is no longer valid."}}
        if state == "missing" or req is None:
            return 404, {"error": {"code": "REQUEST_NOT_FOUND", "message": "Request not found."}}
        if state == "receipt" and receipt:
            return receipt.status_code, receipt.response
        if state == "invalid":
            return 400, {"error": {"code": "INVALID_RESUME_NONCE", "message": "Nonce was not issued for this request and waiting generation."}}
        if state == "busy":
            return 202, {
                "status": req.status, "request_id": req.id, "active_job_id": req.active_job_id,
                "message": "Continuation is already in progress.",
            }

        generation = req.generation
        if req.status == "WAITING_FOR_JOB" and not req.active_job_id:
            try:
                _, response, _ = self.store.finish_request(
                    req.id, generation, worker_id, "FAILED",
                    {"status": "FAILED", "summary": "The waiting request has no attached job."},
                    {"code": "JOB_NOT_FOUND", "message": "The attached job could not be recovered."},
                    nonce, self._response_factory,
                )
                saved = self.store.get_receipt(req.id, nonce)
                return (saved.status_code, saved.response) if saved else (500, response)
            except LeaseLostError:
                return 202, {"status": req.status, "request_id": req.id, "message": "Retry in progress."}

        if req.active_job_id:
            try:
                state, code, response, current = self.store.process_active_job(
                    request_id=req.id, expected_generation=generation, worker_id=worker_id,
                    session_token=self.session_token, continuation_nonce=nonce,
                    response_factory=self._response_factory, safe_error=_safe_public_error,
                )
            except (LeaseLostError, InvalidContinuationNonce):
                latest = self._get_required_request(req.id)
                return 202, {"status": latest.status, "request_id": req.id, "message": "Retry in progress."}
            if state == "waiting":
                saved = self.store.get_receipt(req.id, nonce)
                return (saved.status_code, saved.response) if saved else (code, response)
            req = current

        final_req = await self._run_owned_request(req, generation, worker_id, nonce)
        saved = self.store.get_receipt(request_id, nonce)
        if saved:
            return saved.status_code, saved.response
        if final_req.status in ("COMPLETED", "FAILED", "CANCELLED"):
            return (500 if final_req.status == "FAILED" else 200), format_agent_response(final_req, self.store)
        return 202, format_agent_response(final_req, self.store)
