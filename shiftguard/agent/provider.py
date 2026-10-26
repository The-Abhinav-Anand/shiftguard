"""Provider adapter for Nebius Token Factory (Nemotron-3_5-Lightning) and ScriptedProvider."""

from __future__ import annotations

import asyncio
import logging
import json
import re
from typing import Any, Protocol, Sequence
from pydantic import BaseModel

import openai
from openai import AsyncOpenAI

from shiftguard.agent.budget import (
    AttemptBudget,
    AttemptReservation,
    BudgetBoundExceeded,
    BudgetHalted,
    BudgetLimitExceeded,
    BudgetUsageInvalid,
)
from shiftguard.agent.policy import AgentErrorCode
from shiftguard.agent.ordinary_budget import (
    ORDINARY_MAX_OUTPUT_TOKENS,
    OrdinaryBudget,
    OrdinaryBudgetBoundExceeded,
    OrdinaryBudgetHalted,
    OrdinaryBudgetLimitExceeded,
    OrdinaryBudgetUsageInvalid,
    OrdinaryReservation,
)
from shiftguard.agent.ordinary_owner import OrdinaryOwnerUnavailable
from shiftguard.agent.schemas import FunctionCall, ToolCall
from shiftguard.settings import Settings

logger = logging.getLogger(__name__)

MAX_TRANSCRIPT_BYTES = 64 * 1024
MAX_MESSAGES = 64
MAX_TOOL_DEFINITIONS = 12
MAX_TOOL_CALLS_PER_RESPONSE = 12
MAX_CONTENT_BYTES = 16 * 1024
MAX_TOOL_ARGUMENT_BYTES = 8 * 1024
MAX_PROVIDER_ID_BYTES = 256


def redact_secrets(text: str, known_secret: str | None = None) -> str:
    """Sanitize strings to ensure API keys, tokens, or bearer headers are never logged or stored."""
    if not text:
        return text
    if known_secret:
        text = text.replace(known_secret, "[REDACTED]")
    # Redact Bearer tokens
    sanitized = re.sub(r"(Bearer\s+)[A-Za-z0-9_\-\.]{8,}", r"\1[REDACTED]", text, flags=re.IGNORECASE)
    # Redact key-like hex/alphanumeric sequences over 20 chars
    sanitized = re.sub(r"(key[=:\s]+)[A-Za-z0-9_\-\.]{16,}", r"\1[REDACTED]", sanitized, flags=re.IGNORECASE)
    return sanitized


class ProviderResponse(BaseModel):
    content: str | None = None
    tool_calls: list[ToolCall] | None = None
    finish_reason: str | None = None
    usage: dict[str, int] | None = None
    provider_request_id: str | None = None
    is_mock: bool = False


class ProviderError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int | None = None,
        raw_error: str | None = None,
        dispatched: bool = True,
    ):
        safe_message = redact_secrets(message)
        super().__init__(safe_message)
        self.code = code
        self.message = safe_message
        self.status_code = status_code
        # False only when no request can have left this process. Anything else
        # may have reached the provider and must be treated as possibly billed.
        self.dispatched = dispatched
        # Never retain arbitrary upstream text. The legacy field remains available,
        # but carries only a fixed marker when a raw detail was supplied.
        self.raw_error = "[redacted provider detail]" if raw_error else None


class ProviderDisabledError(ProviderError):
    def __init__(self, message: str = "Agent provider is disabled or credentials are unconfigured"):
        super().__init__(
            code=AgentErrorCode.PROVIDER_DISABLED, message=message, status_code=503,
            dispatched=False,
        )


class ProviderClient(Protocol):
    async def chat(
        self,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None = None,
    ) -> ProviderResponse:
        ...

    async def close(self) -> None:
        ...


class AgentProvider:
    """Async OpenAI-compatible client adapter targeting Nebius Token Factory."""

    def __init__(
        self,
        settings: Settings,
        *,
        attempt_budget: AttemptBudget | None = None,
        ordinary_budget: OrdinaryBudget | None = None,
    ) -> None:
        self.settings = settings
        self.agent_enabled = bool(getattr(settings, "agent_enabled", False))
        self.general_chat_enabled = bool(getattr(settings, "general_chat_enabled", False))
        self.enabled = self.agent_enabled or self.general_chat_enabled
        self.api_key = getattr(settings, "nebius_api_key", None)
        self.base_url = getattr(settings, "nebius_base_url", "https://api.tokenfactory.nebius.com/v1")
        self.model = getattr(settings, "nebius_model", "nvidia/Nemotron-3_5-Lightning")
        self.timeout = float(getattr(settings, "nebius_timeout", 25.0))
        self.max_retries = 0
        self.max_output_tokens = int(getattr(settings, "nebius_max_output_tokens", 1024))
        self.ordinary_budget = ordinary_budget
        if ordinary_budget is not None:
            self.max_output_tokens = min(self.max_output_tokens, ORDINARY_MAX_OUTPUT_TOKENS)
        self.chat_template_kwargs = settings.nebius_chat_template_kwargs
        if attempt_budget is not None and not isinstance(attempt_budget, AttemptBudget):
            raise TypeError("live provider budget must be an AttemptBudget")
        self.attempt_budget = (
            attempt_budget
            if attempt_budget is not None
            else (
                AttemptBudget.from_invocation_environment(settings)
                if self.agent_enabled
                else None
            )
        )

        self._client: AsyncOpenAI | None = None
        if self.enabled and self.api_key and self.api_key.strip():
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
                max_retries=0,
            )

    def is_available(self) -> bool:
        return self._client is not None

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
        if self.attempt_budget is not None:
            self.attempt_budget.close()

    async def chat(
        self,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None = None,
    ) -> ProviderResponse:
        """Results-assistant dispatch. Only the agent flag opens it."""
        return await self._dispatch(messages, tools, allowed=self.agent_enabled)

    async def general_chat(self, messages: Sequence[dict[str, Any]]) -> ProviderResponse:
        """Ordinary conversation. Only its own flag opens it, and it never carries tools."""
        return await self._dispatch(messages, None, allowed=self.general_chat_enabled)

    async def _dispatch(
        self,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None,
        *,
        allowed: bool,
    ) -> ProviderResponse:
        if not allowed or self._client is None:
            raise ProviderDisabledError(
                "Nemotron provider is disabled or NEBIUS_API_KEY is missing. "
                "Manual workbench presets and cached results remain fully operational."
            )

        reservation: AttemptReservation | None = None
        ordinary_reservation: OrdinaryReservation | None = None
        dispatched = False

        def close_unknown(failure_kind: str) -> None:
            nonlocal reservation, ordinary_reservation
            if reservation is not None and self.attempt_budget is not None:
                try:
                    self.attempt_budget.close_unknown(reservation, failure_kind)
                except Exception as close_error:
                    logger.error("Provider budget attempt close failed (%s)", type(close_error).__name__)
                reservation = None
            if ordinary_reservation is not None and self.ordinary_budget is not None:
                try:
                    self.ordinary_budget.close_unknown(ordinary_reservation, failure_kind)
                except Exception as close_error:
                    logger.error("Ordinary provider budget close failed (%s)", type(close_error).__name__)
                ordinary_reservation = None

        def close_timeout() -> None:
            """Timeout: the sealed attempt ledger halts; the ordinary day is charged but stays open."""
            nonlocal reservation, ordinary_reservation
            if reservation is not None and self.attempt_budget is not None:
                try:
                    self.attempt_budget.close_unknown(reservation, "timeout")
                except Exception as close_error:
                    logger.error("Provider budget attempt close failed (%s)", type(close_error).__name__)
                reservation = None
            if ordinary_reservation is not None and self.ordinary_budget is not None:
                try:
                    if self.ordinary_budget.close_timeout(ordinary_reservation) == 0:
                        logger.warning("Ordinary provider budget timeout close changed no row")
                except Exception as close_error:
                    logger.error("Ordinary provider budget timeout close failed (%s)", type(close_error).__name__)
                    # Failing to record must stay fail-closed: fall back to halting the day.
                    try:
                        self.ordinary_budget.close_unknown(ordinary_reservation, "timeout")
                    except Exception as fallback_error:
                        logger.error(
                            "Ordinary provider budget close failed (%s)", type(fallback_error).__name__
                        )
                ordinary_reservation = None

        try:
            normalized_messages = _validate_messages(messages)
            normalized_tools = _validate_tools(tools)
            if self.ordinary_budget is not None:
                try:
                    ordinary_reservation = self.ordinary_budget.reserve(
                        model=self.model,
                        messages=normalized_messages,
                        tools=normalized_tools,
                        max_output_tokens=self.max_output_tokens,
                    )
                except OrdinaryBudgetLimitExceeded as err:
                    raise ProviderError(
                        code="ORDINARY_BUDGET_EXCEEDED",
                        message=f"The ordinary provider daily {err.limit} allowance is exhausted.",
                        status_code=429,
                    ) from None
                except OrdinaryBudgetHalted as err:
                    raise ProviderError(
                        code="ORDINARY_BUDGET_HALTED",
                        message=f"The ordinary provider daily ledger is halted ({err.reason}).",
                        status_code=429,
                    ) from None
                except OrdinaryOwnerUnavailable:
                    raise ProviderError(
                        code="ORDINARY_OWNER_UNAVAILABLE",
                        message="This server no longer owns ordinary provider dispatch; restart it to recover.",
                        status_code=503,
                    ) from None
            if self.attempt_budget is not None:
                try:
                    reservation = self.attempt_budget.reserve(
                        model=self.model,
                        messages=normalized_messages,
                        tools=normalized_tools,
                        max_output_tokens=self.max_output_tokens,
                    )
                except BudgetLimitExceeded as err:
                    if ordinary_reservation is not None and self.ordinary_budget is not None:
                        self.ordinary_budget.release_unstarted(ordinary_reservation)
                        ordinary_reservation = None
                    raise ProviderError(
                        code="BUDGET_EXCEEDED",
                        message=f"The live provider {err.limit} allowance is exhausted.",
                        status_code=429,
                    ) from None
                except BudgetHalted as err:
                    if ordinary_reservation is not None and self.ordinary_budget is not None:
                        self.ordinary_budget.release_unstarted(ordinary_reservation)
                        ordinary_reservation = None
                    raise ProviderError(
                        code="BUDGET_HALTED",
                        message=f"The live provider ledger is halted ({err.reason}).",
                        status_code=429,
                    ) from None
            kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": normalized_messages,
                "max_tokens": self.max_output_tokens,
                "extra_body": {"chat_template_kwargs": self.chat_template_kwargs},
            }
            if normalized_tools:
                kwargs["tools"] = normalized_tools
                kwargs["tool_choice"] = "auto"
            dispatched = True
            try:
                async with asyncio.timeout(self.timeout):
                    resp = await self._client.chat.completions.create(**kwargs)
            except (openai.APITimeoutError, TimeoutError) as err:
                # Only the dispatch itself is exempt from halting; a timeout raised anywhere
                # else in this block falls through to the fail-closed handlers below.
                close_timeout()
                is_sdk_timeout = isinstance(err, openai.APITimeoutError)
                logger.warning(
                    "Provider request failed: %s",
                    "timeout" if is_sdk_timeout else "total deadline exceeded",
                )
                raise ProviderError(
                    code="PROVIDER_TIMEOUT",
                    message="Provider request timed out. Please try again.",
                    status_code=504,
                    raw_error=str(err) if is_sdk_timeout else "total deadline exceeded",
                ) from None
            parsed = _parse_provider_response(resp, expected_model=self.model)
            if ordinary_reservation is not None and self.ordinary_budget is not None:
                try:
                    self.ordinary_budget.settle(
                        ordinary_reservation, parsed.usage, parsed.provider_request_id
                    )
                except OrdinaryBudgetBoundExceeded:
                    ordinary_reservation = None
                    raise ProviderError(
                        code="ORDINARY_BUDGET_EXCEEDED",
                        message="Provider usage exceeded its ordinary daily reservation; the daily ledger is halted and actual usage is charged.",
                        status_code=502,
                    ) from None
                except OrdinaryBudgetUsageInvalid:
                    close_unknown("invalid_usage")
                    raise ProviderError(
                        code="PROVIDER_INVALID_RESPONSE",
                        message="Provider usage was missing or invalid; the ordinary daily ledger is halted.",
                        status_code=502,
                    ) from None
                ordinary_reservation = None
            if reservation is not None and self.attempt_budget is not None:
                try:
                    self.attempt_budget.settle(
                        reservation, parsed.usage, parsed.provider_request_id
                    )
                except BudgetBoundExceeded:
                    reservation = None
                    raise ProviderError(
                        code="BUDGET_EXCEEDED",
                        message="Provider usage exceeded a reserved component bound; the ledger is halted and the actual usage is charged.",
                        status_code=502,
                    ) from None
                except BudgetUsageInvalid:
                    close_unknown("invalid_usage")
                    raise ProviderError(
                        code="PROVIDER_INVALID_RESPONSE",
                        message="Provider usage was missing or invalid; the attempt remains charged.",
                        status_code=502,
                    ) from None
                reservation = None
            return parsed
        except openai.APITimeoutError as err:
            close_unknown("timeout")
            logger.warning("Provider request failed: timeout")
            raise ProviderError(
                code="PROVIDER_TIMEOUT",
                message="Provider request timed out. Please try again.",
                status_code=504,
                raw_error=str(err),
            ) from None
        except TimeoutError:
            close_unknown("timeout")
            logger.warning("Provider request failed: total deadline exceeded")
            raise ProviderError(
                code="PROVIDER_TIMEOUT",
                message="Provider request timed out. Please try again.",
                status_code=504,
                raw_error="total deadline exceeded",
            ) from None
        except asyncio.CancelledError:
            close_unknown("unknown")
            raise
        except openai.RateLimitError as err:
            close_unknown("provider_error")
            logger.warning("Provider request failed: rate limited")
            raise ProviderError(
                code="PROVIDER_RATE_LIMIT",
                message="Provider rate limit exceeded. Please wait before retrying.",
                status_code=429,
                raw_error=str(err),
            ) from None
        except openai.AuthenticationError as err:
            close_unknown("provider_error")
            logger.error("Provider request failed: authentication")
            raise ProviderError(
                code="PROVIDER_AUTH_ERROR",
                message="Invalid or unauthorized Nebius API key.",
                status_code=401,
                raw_error=str(err),
            ) from None
        except openai.NotFoundError as err:
            close_unknown("provider_error")
            logger.error("Provider request failed: model not found")
            raise ProviderError(
                code="PROVIDER_MODEL_NOT_FOUND",
                message="Configured provider model was not found or is inaccessible.",
                status_code=404,
                raw_error=str(err),
            ) from None
        except openai.InternalServerError as err:
            close_unknown("provider_error")
            logger.error("Provider request failed: upstream server error")
            raise ProviderError(
                code="PROVIDER_SERVER_ERROR",
                message="Nebius Token Factory service error. Please try again later.",
                status_code=502,
                raw_error=str(err),
            ) from None
        except openai.APIConnectionError as err:
            close_unknown("provider_error")
            logger.warning("Provider request failed: connection")
            raise ProviderError(
                code="PROVIDER_CONNECTION_ERROR",
                message="Could not connect to Nebius Token Factory endpoint.",
                status_code=503,
                raw_error=str(err),
            ) from None
        except ProviderError as err:
            close_unknown("provider_error")
            err.dispatched = dispatched
            raise
        except (ValueError, TypeError, KeyError, AttributeError, IndexError, json.JSONDecodeError) as err:
            close_unknown("invalid_usage")
            logger.warning("Provider request failed: invalid response or request shape")
            raise ProviderError(
                code="PROVIDER_INVALID_RESPONSE",
                message="Provider returned an invalid response or the request exceeded configured bounds.",
                status_code=502,
                raw_error=type(err).__name__,
                dispatched=dispatched,
            ) from None
        except Exception as err:
            close_unknown("provider_error")
            logger.error("Provider request failed: unexpected error (%s)", type(err).__name__)
            raise ProviderError(
                code=AgentErrorCode.PROVIDER_ERROR,
                message="Provider request failed. Please try again later.",
                status_code=502,
                raw_error=type(err).__name__,
                dispatched=dispatched,
            ) from None


def _json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("request is not bounded JSON") from exc


def _validate_messages(messages: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(messages, (str, bytes)) or not isinstance(messages, Sequence):
        raise ValueError("messages must be a sequence")
    normalized = list(messages)
    if not normalized or len(normalized) > MAX_MESSAGES:
        raise ValueError("message count outside configured bounds")
    allowed = {"role", "content", "name", "tool_call_id", "tool_calls"}
    for message in normalized:
        if not isinstance(message, dict) or set(message) - allowed:
            raise ValueError("invalid message fields")
        role = message.get("role")
        if role not in {"system", "user", "assistant", "tool"}:
            raise ValueError("invalid message role")
        content = message.get("content")
        if content is not None and not isinstance(content, str):
            raise ValueError("message content must be text or null")
        if role == "tool" and not isinstance(message.get("tool_call_id"), str):
            raise ValueError("tool response must identify its call")
        if "tool_call_id" in message and not _valid_bounded_string(message["tool_call_id"], MAX_PROVIDER_ID_BYTES):
            raise ValueError("invalid tool call identifier")
        if "name" in message and not _valid_bounded_string(message["name"], 128):
            raise ValueError("invalid message name")
        if "tool_calls" in message:
            calls = message["tool_calls"]
            if role != "assistant" or not isinstance(calls, list) or len(calls) > MAX_TOOL_CALLS_PER_RESPONSE:
                raise ValueError("invalid assistant tool calls")
            ids: set[str] = set()
            for call in calls:
                if not isinstance(call, dict) or set(call) != {"id", "type", "function"} or call.get("type") != "function":
                    raise ValueError("invalid assistant tool call")
                call_id = call.get("id")
                function = call.get("function")
                if not _valid_bounded_string(call_id, MAX_PROVIDER_ID_BYTES) or call_id in ids:
                    raise ValueError("invalid or duplicate tool call identifier")
                ids.add(call_id)
                if not isinstance(function, dict) or set(function) != {"name", "arguments"}:
                    raise ValueError("invalid function call")
                if not _valid_tool_name(function.get("name")) or not isinstance(function.get("arguments"), str):
                    raise ValueError("invalid function call shape")
                if len(function["arguments"].encode("utf-8")) > MAX_TOOL_ARGUMENT_BYTES:
                    raise ValueError("tool arguments exceed configured bounds")
                parsed = json.loads(function["arguments"])
                if not isinstance(parsed, dict):
                    raise ValueError("tool arguments must be a JSON object")
    if len(_json_bytes(normalized)) > MAX_TRANSCRIPT_BYTES:
        raise ValueError("transcript exceeds configured byte limit")
    return normalized


def _validate_tools(tools: Sequence[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    if tools is None:
        return None
    if isinstance(tools, (str, bytes)) or not isinstance(tools, Sequence) or len(tools) > MAX_TOOL_DEFINITIONS:
        raise ValueError("tool definitions exceed configured bounds")
    normalized = list(tools)
    for item in normalized:
        if not isinstance(item, dict) or set(item) != {"type", "function"} or item.get("type") != "function":
            raise ValueError("invalid tool definition")
        function = item.get("function")
        if not isinstance(function, dict) or not _valid_tool_name(function.get("name")):
            raise ValueError("invalid tool function definition")
        if len(_json_bytes(item)) > MAX_TOOL_ARGUMENT_BYTES:
            raise ValueError("tool definition exceeds configured bounds")
    if len(_json_bytes(normalized)) > MAX_TRANSCRIPT_BYTES:
        raise ValueError("tool definitions exceed configured byte limit")
    return normalized


def _valid_bounded_string(value: Any, max_bytes: int) -> bool:
    return isinstance(value, str) and bool(value) and len(value.encode("utf-8")) <= max_bytes


def _valid_tool_name(value: Any) -> bool:
    return isinstance(value, str) and len(value) <= 128 and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value) is not None


def _parse_provider_response(resp: Any, expected_model: str) -> ProviderResponse:
    model = getattr(resp, "model", None)
    if not _valid_bounded_string(model, MAX_PROVIDER_ID_BYTES) or model != expected_model:
        raise ValueError("provider model is missing or does not match configured model")
    choices = getattr(resp, "choices", None)
    if not isinstance(choices, (list, tuple)) or not choices or len(choices) > 16:
        raise ValueError("provider returned no valid choices")
    choice = choices[0]
    message = getattr(choice, "message", None)
    if message is None:
        raise ValueError("provider returned no message")
    content = getattr(message, "content", None)
    if content is not None and (not isinstance(content, str) or len(content.encode("utf-8")) > MAX_CONTENT_BYTES):
        raise ValueError("provider content outside configured bounds")
    raw_calls = getattr(message, "tool_calls", None)
    parsed_calls: list[ToolCall] | None = None
    if raw_calls:
        if not isinstance(raw_calls, (list, tuple)) or len(raw_calls) > MAX_TOOL_CALLS_PER_RESPONSE:
            raise ValueError("provider tool call count outside configured bounds")
        parsed_calls = []
        seen_ids: set[str] = set()
        for raw_call in raw_calls:
            call_id = getattr(raw_call, "id", None)
            function = getattr(raw_call, "function", None)
            name = getattr(function, "name", None)
            arguments = getattr(function, "arguments", None)
            if not _valid_bounded_string(call_id, MAX_PROVIDER_ID_BYTES) or call_id in seen_ids:
                raise ValueError("provider tool call has invalid identifier")
            if not _valid_tool_name(name) or not isinstance(arguments, str) or len(arguments.encode("utf-8")) > MAX_TOOL_ARGUMENT_BYTES:
                raise ValueError("provider tool call exceeds configured bounds")
            parsed_arguments = json.loads(arguments)
            if not isinstance(parsed_arguments, dict):
                raise ValueError("provider tool arguments must be a JSON object")
            seen_ids.add(call_id)
            parsed_calls.append(ToolCall(id=call_id, type="function", function=FunctionCall(name=name, arguments=arguments)))
    finish_reason = getattr(choice, "finish_reason", None)
    if finish_reason is not None and (not isinstance(finish_reason, str) or len(finish_reason) > 64):
        raise ValueError("invalid provider finish reason")
    request_id = getattr(resp, "id", None)
    if request_id is not None and not _valid_bounded_string(request_id, MAX_PROVIDER_ID_BYTES):
        raise ValueError("invalid provider request id")
    raw_usage = getattr(resp, "usage", None)
    usage: dict[str, int] | None = None
    if raw_usage is not None:
        values = {name: getattr(raw_usage, name, None) for name in ("prompt_tokens", "completion_tokens", "total_tokens")}
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in values.values()):
            raise ValueError("invalid provider usage")
        if values["total_tokens"] < values["prompt_tokens"] or values["total_tokens"] < values["completion_tokens"]:
            raise ValueError("inconsistent provider usage")
        details = getattr(raw_usage, "completion_tokens_details", None)
        reasoning_tokens = getattr(details, "reasoning_tokens", None)
        if (
            isinstance(reasoning_tokens, int)
            and not isinstance(reasoning_tokens, bool)
            and 0 <= reasoning_tokens <= values["completion_tokens"]
        ):
            values["reasoning_tokens"] = reasoning_tokens
        usage = values
    return ProviderResponse(
        content=content,
        tool_calls=parsed_calls,
        finish_reason=finish_reason,
        usage=usage,
        provider_request_id=request_id,
        is_mock=False,
    )


class ScriptedProvider:
    """Deterministic scripted provider for isolated contract and integration testing."""

    def __init__(self, responses: Sequence[ProviderResponse | Exception] | None = None) -> None:
        self.responses: list[ProviderResponse | Exception] = list(responses or [])
        self.history: list[dict[str, Any]] = []
        self._index: int = 0

    def add_response(self, response: ProviderResponse | Exception) -> None:
        self.responses.append(response)

    def is_available(self) -> bool:
        return True

    async def chat(
        self,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None = None,
    ) -> ProviderResponse:
        self.history.append({
            "messages": list(messages),
            "tools": list(tools) if tools else None,
        })
        if self._index >= len(self.responses):
            return ProviderResponse(
                content="Scripted default: No more scripted turns configured.",
                tool_calls=None,
                finish_reason="stop",
                is_mock=True,
            )

        resp = self.responses[self._index]
        self._index += 1

        if isinstance(resp, Exception):
            raise resp

        # Ensure is_mock is marked True
        resp.is_mock = True
        return resp

    async def close(self) -> None:
        pass


class DynamicE2EProvider:
    """Dynamic scripted provider for Playwright E2E browser verification.

    Responds deterministically based on tool history, invoking real backend tools
    (inspect_dataset, run_experiment, read_experiment_results) and asserting
    real execution without external API dependencies.
    """

    def __init__(self) -> None:
        self.history: list[dict[str, Any]] = []

    def is_available(self) -> bool:
        return True

    async def chat(
        self,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None = None,
    ) -> ProviderResponse:
        import json

        self.history.append({
            "messages": list(messages),
            "tools": list(tools) if tools else None,
        })

        # Analyze messages to see what tool calls have already been executed
        tool_results: list[dict[str, Any]] = [m for m in messages if m.get("role") == "tool"]

        user_msgs = [m for m in messages if m.get("role") == "user"]
        prompt = user_msgs[-1].get("content", "").lower() if user_msgs else ""

        if not tool_results:
            if "dataset" in prompt or "inspect" in prompt:
                return ProviderResponse(
                    content=None,
                    tool_calls=[
                        ToolCall(
                            id="e2e_call_inspect_1",
                            function=FunctionCall(
                                name="inspect_dataset",
                                arguments=json.dumps({"dataset_id": "bank"}),
                            ),
                        )
                    ],
                    finish_reason="tool_calls",
                    is_mock=True,
                )
            else:
                return ProviderResponse(
                    content=None,
                    tool_calls=[
                        ToolCall(
                            id="e2e_call_run_1",
                            function=FunctionCall(
                                name="run_experiment",
                                arguments=json.dumps({"preset_name": "bank-outage-50"}),
                            ),
                        )
                    ],
                    finish_reason="tool_calls",
                    is_mock=True,
                )

        last_tool = tool_results[-1]
        last_name = last_tool.get("name")

        if last_name == "inspect_dataset":
            return ProviderResponse(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="e2e_call_run_2",
                        function=FunctionCall(
                            name="run_experiment",
                            arguments=json.dumps({"preset_name": "bank-outage-50"}),
                        ),
                    )
                ],
                finish_reason="tool_calls",
                is_mock=True,
            )

        # Check if read_experiment_results has already been called
        has_read = any(
            t.get("name") == "read_experiment_results" or "read_experiment_results" in str(t.get("content", ""))
            for t in tool_results
        )

        if not has_read:
            # Look for an experiment_id in tool results
            exp_id = None
            for tr in reversed(tool_results):
                try:
                    c = json.loads(tr.get("content", "{}"))
                    exp_id = (c.get("data") or {}).get("experiment_id") or c.get("experiment_id")
                    if exp_id:
                        break
                except Exception:
                    continue

            if exp_id:
                return ProviderResponse(
                    content=None,
                    tool_calls=[
                        ToolCall(
                            id="e2e_call_read_1",
                            function=FunctionCall(
                                name="read_experiment_results",
                                arguments=json.dumps({"experiment_id": exp_id}),
                            ),
                        )
                    ],
                    finish_reason="tool_calls",
                    is_mock=True,
                )

        return ProviderResponse(
            content=(
                "Completed run and evaluation of bank-outage-50. "
                "Persisted metrics, reliability bins, and decision loss curves are verified."
            ),
            tool_calls=None,
            finish_reason="stop",
            is_mock=True,
        )

    async def close(self) -> None:
        pass


def create_e2e_scripted_provider() -> DynamicE2EProvider:
    return DynamicE2EProvider()
