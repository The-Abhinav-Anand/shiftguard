"""Tool registry and dispatcher for Gate 6 bounded agent."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Type
from pydantic import BaseModel, ValidationError

from shiftguard.agent.policy import AgentErrorCode, safe_tool_call_id
from shiftguard.agent.schemas import (
    CalculateDecisionLossParams,
    CompareCalibratorsParams,
    CompareOutagesParams,
    GenerateResultSummaryParams,
    GetExperimentMetadataParams,
    GetLabelBudgetCurveParams,
    InspectDatasetParams,
    InspectMissingnessParams,
    ListAvailableScenariosParams,
    ReadExperimentResultsParams,
    RunExperimentParams,
    RunStressSuiteParams,
    ToolResult,
)
from shiftguard.agent.tools import ToolContext
from shiftguard.agent.tools.metadata import (
    inspect_dataset,
    inspect_missingness,
    list_available_scenarios,
)
from shiftguard.agent.tools.results import (
    calculate_decision_loss,
    compare_calibrators,
    compare_outages,
    generate_result_summary,
    get_experiment_metadata,
    get_label_budget_curve,
    read_experiment_results,
)
from shiftguard.agent.tools.runs import (
    run_experiment,
    run_stress_suite,
)

MAX_TOOL_ARGUMENT_BYTES = 8192
_SAFE_PROVIDER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


@dataclass(frozen=True)
class PreparedToolArguments:
    """Value-free validation outcome reusable before transcript persistence."""

    params: BaseModel | None
    accepted_arguments: dict[str, Any]
    rejection_code: str | None = None
    rejected_fields: tuple[str, ...] = ()
    rejection_detail: str | None = None

    @property
    def ok(self) -> bool:
        return self.params is not None

    @property
    def safe_error(self) -> str | None:
        if self.ok:
            return None
        if self.rejection_detail:
            return f"{self.rejection_code or AgentErrorCode.INVALID_ARGUMENTS}: {self.rejection_detail}"
        suffix = f" (fields: {', '.join(self.rejected_fields)})" if self.rejected_fields else ""
        return f"{self.rejection_code or AgentErrorCode.INVALID_ARGUMENTS}: Arguments were rejected{suffix}."


def _json_argument_size(value: Any) -> int | None:
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        return len(encoded.encode("utf-8"))
    except (TypeError, ValueError, RecursionError):
        return None


def _safe_validation_fields(err: ValidationError, model: Type[BaseModel]) -> tuple[str, ...]:
    declared = set(model.model_fields)
    fields: set[str] = set()
    for item in err.errors(include_input=False, include_context=False, include_url=False):
        loc = item.get("loc") or ()
        first = str(loc[0]) if loc else "invalid"
        fields.add(first if first in declared else "extra")
    return tuple(sorted(fields))[:16]


class ToolEntry:
    def __init__(
        self,
        name: str,
        description: str,
        param_model: Type[BaseModel],
        handler: Callable[[Any, ToolContext, str], ToolResult],
        is_side_effect: bool = False,
    ):
        self.name = name
        self.description = description
        self.param_model = param_model
        self.handler = handler
        self.is_side_effect = is_side_effect


class ToolRegistry:
    """Strict twelve-tool registry enforcing type safety, exact IDs, and side-effect tracking."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolEntry] = {}
        self._register_default_tools()

    def _register(
        self,
        name: str,
        description: str,
        param_model: Type[BaseModel],
        handler: Callable[[Any, ToolContext, str], ToolResult],
        is_side_effect: bool = False,
    ) -> None:
        self._tools[name] = ToolEntry(
            name=name,
            description=description,
            param_model=param_model,
            handler=handler,
            is_side_effect=is_side_effect,
        )

    def _register_default_tools(self) -> None:
        # 1. inspect_dataset
        self._register(
            name="inspect_dataset",
            description="Inspect dataset metadata, features, and natural missingness contract for Bank marketing.",
            param_model=InspectDatasetParams,
            handler=inspect_dataset,
            is_side_effect=False,
        )
        # 2. list_available_scenarios
        self._register(
            name="list_available_scenarios",
            description="List executable development scenarios, approved presets, and allowed parameters.",
            param_model=ListAvailableScenariosParams,
            handler=list_available_scenarios,
            is_side_effect=False,
        )
        # 3. inspect_missingness
        self._register(
            name="inspect_missingness",
            description="Inspect missingness injection parameters or realized rates from a published experiment.",
            param_model=InspectMissingnessParams,
            handler=inspect_missingness,
            is_side_effect=False,
        )
        # 4. run_experiment (side effect)
        self._register(
            name="run_experiment",
            description="Compile a supported intent into bank-baseline, bank-stress, or bank-outage-50 (seed 31001) and enqueue durably.",
            param_model=RunExperimentParams,
            handler=run_experiment,
            is_side_effect=True,
        )
        # 5. run_stress_suite (side effect)
        self._register(
            name="run_stress_suite",
            description="Map bank-stress, bank-stress-30, or flagship-stress to bank-stress and enqueue durably.",
            param_model=RunStressSuiteParams,
            handler=run_stress_suite,
            is_side_effect=True,
        )
        # 6. compare_outages
        self._register(
            name="compare_outages",
            description="Read persisted paired pattern comparison (block outage vs matched MCAR) at evaluation budget.",
            param_model=CompareOutagesParams,
            handler=compare_outages,
            is_side_effect=False,
        )
        # 7. compare_calibrators
        self._register(
            name="compare_calibrators",
            description="Compare calibration methods on a matching scenario, predictor, and label budget.",
            param_model=CompareCalibratorsParams,
            handler=compare_calibrators,
            is_side_effect=False,
        )
        # 8. get_label_budget_curve
        self._register(
            name="get_label_budget_curve",
            description="Read the saved label budget curve at supported budgets 0, 25, 50, 100, or 200.",
            param_model=GetLabelBudgetCurveParams,
            handler=get_label_budget_curve,
            is_side_effect=False,
        )
        # 9. calculate_decision_loss
        self._register(
            name="calculate_decision_loss",
            description="Return exact persisted decision loss from cost grid for requested condition. Supported cost pairs: (1,1), (1,4), (4,1), (1,9), (9,1).",
            param_model=CalculateDecisionLossParams,
            handler=calculate_decision_loss,
            is_side_effect=False,
        )
        # 10. read_experiment_results
        self._register(
            name="read_experiment_results",
            description="Read published condition metrics, diagnostics, and sparse-bin fields from an experiment.",
            param_model=ReadExperimentResultsParams,
            handler=read_experiment_results,
            is_side_effect=False,
        )
        # 11. get_experiment_metadata
        self._register(
            name="get_experiment_metadata",
            description="Read persisted experiment configuration, seeds, provenance, and content hashes.",
            param_model=GetExperimentMetadataParams,
            handler=get_experiment_metadata,
            is_side_effect=False,
        )
        # 12. generate_result_summary
        self._register(
            name="generate_result_summary",
            description="Generate a deterministic summary for authorized evidence; focus defaults to all (all, fallback, outages, calibration).",
            param_model=GenerateResultSummaryParams,
            handler=generate_result_summary,
            is_side_effect=False,
        )

    def get_tool_names(self) -> list[str]:
        return sorted(list(self._tools.keys()))

    def is_side_effect(self, name: str) -> bool:
        entry = self._tools.get(name)
        return entry.is_side_effect if entry else False

    def get_openai_tool_definitions(self) -> list[dict[str, Any]]:
        """Generate OpenAI-compatible tool schemas for Nemotron provider."""
        defs = []
        for name in sorted(self._tools.keys()):
            entry = self._tools[name]
            schema = entry.param_model.model_json_schema()
            # Clean up schema for provider consumption
            schema.pop("title", None)
            defs.append({
                "type": "function",
                "function": {
                    "name": entry.name,
                    "description": entry.description,
                    "parameters": schema,
                },
            })
        return defs

    def prepare_arguments(self, name: str, raw_arguments: str | dict[str, Any]) -> PreparedToolArguments:
        """Validate a provider tool payload and retain only accepted allowlisted values."""
        entry = self._tools.get(name)
        if entry is None:
            return PreparedToolArguments(None, {}, AgentErrorCode.TOOL_NOT_FOUND)
        if isinstance(raw_arguments, str):
            try:
                size = len(raw_arguments.encode("utf-8"))
            except UnicodeEncodeError:
                return PreparedToolArguments(None, {}, AgentErrorCode.INVALID_ARGUMENTS)
            if size > MAX_TOOL_ARGUMENT_BYTES:
                return PreparedToolArguments(None, {}, AgentErrorCode.INVALID_ARGUMENTS)
            try:
                parsed_args = json.loads(raw_arguments) if raw_arguments.strip() else {}
            except (json.JSONDecodeError, RecursionError):
                return PreparedToolArguments(None, {}, AgentErrorCode.INVALID_ARGUMENTS)
        elif isinstance(raw_arguments, dict):
            parsed_args = raw_arguments
        else:
            return PreparedToolArguments(None, {}, AgentErrorCode.INVALID_ARGUMENTS)
        if not isinstance(parsed_args, dict):
            return PreparedToolArguments(None, {}, AgentErrorCode.INVALID_ARGUMENTS)
        size = _json_argument_size(parsed_args)
        if size is None or size > MAX_TOOL_ARGUMENT_BYTES:
            return PreparedToolArguments(None, {}, AgentErrorCode.INVALID_ARGUMENTS)
        try:
            params = entry.param_model.model_validate(parsed_args)
        except ValidationError as err:
            detail = None
            if entry.param_model is InspectMissingnessParams:
                has_scenario = isinstance(parsed_args.get("scenario"), str) and bool(parsed_args["scenario"].strip())
                has_experiment = isinstance(parsed_args.get("experiment_id"), str) and bool(parsed_args["experiment_id"].strip())
                if has_scenario == has_experiment:
                    detail = "Exactly one of scenario or experiment_id is required."
            return PreparedToolArguments(
                None, {}, AgentErrorCode.INVALID_ARGUMENTS,
                _safe_validation_fields(err, entry.param_model), detail,
            )
        except Exception:
            return PreparedToolArguments(None, {}, AgentErrorCode.INVALID_ARGUMENTS)
        return PreparedToolArguments(params, params.model_dump(mode="json"))

    def dispatch(
        self,
        name: str,
        raw_arguments: str | dict[str, Any],
        ctx: ToolContext,
        tool_call_id: str,
    ) -> ToolResult:
        """Validate arguments strictly and dispatch to tool handler."""
        safe_call_id = safe_tool_call_id(tool_call_id)
        if safe_call_id is None:
            return ToolResult(tool_name="unknown_tool", tool_call_id="invalid_call_id", status="error",
                              error=f"{AgentErrorCode.INVALID_ARGUMENTS}: Tool call identifier is invalid.")
        tool_call_id = safe_call_id
        entry = self._tools.get(name)
        if not entry:
            return ToolResult(
                tool_name="unknown_tool",
                tool_call_id=tool_call_id,
                status="error",
                error=f"{AgentErrorCode.TOOL_NOT_FOUND}: Tool is not registered.",
            )
        prepared = self.prepare_arguments(name, raw_arguments)
        if not prepared.ok:
            return ToolResult(tool_name=name, tool_call_id=tool_call_id, status="error", error=prepared.safe_error)
        validated_params = prepared.params
        assert validated_params is not None

        # Check session authority at admission before any side effect execution (G6-S08)
        if entry.is_side_effect:
            from shiftguard.agent.execution_authority import execution_preset, EXECUTION_DENIED_MESSAGE
            if execution_preset(name, prepared.accepted_arguments) not in ctx.authorized_run_presets:
                return ToolResult(tool_name=name, tool_call_id=tool_call_id, status="error",
                                  error=EXECUTION_DENIED_MESSAGE, is_side_effect=False)
            try:
                with ctx.engine.connect() as conn:
                    from sqlalchemy import text
                    stmt = text("SELECT status FROM agent_sessions WHERE id = :sid")
                    row = conn.execute(stmt, {"sid": ctx.session_id}).mappings().fetchone()
                if not row or str(row["status"]).upper() != "ACTIVE":
                    return ToolResult(tool_name=name, tool_call_id=tool_call_id, status="error",
                                      error=f"{AgentErrorCode.UNAUTHORIZED_SESSION}: Session is not active.", is_side_effect=False)
            except Exception:
                return ToolResult(tool_name=name, tool_call_id=tool_call_id, status="error",
                                  error=f"{AgentErrorCode.UNAUTHORIZED_SESSION}: Session authority could not be verified.", is_side_effect=False)

        # Execute handler
        try:
            result = entry.handler(validated_params, ctx, tool_call_id)
            from shiftguard.agent.tools.projections import project_tool_result
            return project_tool_result(result)
        except Exception:
            return ToolResult(
                tool_name=name,
                tool_call_id=tool_call_id,
                status="error",
                error=f"{AgentErrorCode.EXPERIMENT_UNAVAILABLE}: Tool execution could not produce a safe result.",
            )


def prepare_tool_call_arguments(
    tool_name: str,
    raw_arguments: str | dict[str, Any],
    registry: ToolRegistry | None = None,
) -> PreparedToolArguments:
    """Shared controller-facing safe validation API; rejected values are never returned."""
    return (registry or ToolRegistry()).prepare_arguments(tool_name, raw_arguments)


def safe_arguments_for_storage(prepared: PreparedToolArguments) -> dict[str, Any]:
    """Return validated arguments or only a bounded rejection marker for durable traces."""
    if prepared.ok:
        return dict(prepared.accepted_arguments)
    return {"rejected": prepared.rejection_code or AgentErrorCode.INVALID_ARGUMENTS}


def safe_tool_error(error: str | None) -> str | None:
    """Shared public/provider error sanitizer."""
    from shiftguard.agent.tools.projections import sanitize_tool_error
    return sanitize_tool_error(error)


def safe_tool_identifier(value: Any) -> str | None:
    """Accept only bounded provider names/call IDs suitable for trace persistence."""
    return value if isinstance(value, str) and _SAFE_PROVIDER_ID.fullmatch(value) else None
