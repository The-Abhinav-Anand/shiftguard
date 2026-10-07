"""Strict schemas for Gate 6 agent runtime, tool registry, and API communication."""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator


class StrictSchema(BaseModel):
    """Base schema enforcing strict type validation and forbidding extraneous fields."""
    model_config = ConfigDict(strict=True, extra="forbid")


PUBLIC_ERROR_MESSAGES = {
    "INVALID_ARGUMENTS": "Arguments were rejected.",
    "UNAUTHORIZED_SESSION": "Session is not active.",
    "EXECUTION_NOT_AUTHORIZED": "An explicit human command naming this preset is required. Use Run bank-baseline, Run bank-stress, or Run bank-outage-50.",
    "UNAUTHORIZED_EXPERIMENT_REFERENCE": "Experiment reference is not authorized for this request.",
    "UNSUPPORTED_COST_PAIR": "Requested cost pair is outside the persisted grid.",
    "UNSUPPORTED_PARAMETER": "Requested value is unsupported.",
    "UNSUPPORTED_COMBINATION": "Requested combination is unsupported.",
    "EXPERIMENT_NOT_FOUND": "Published experiment was not found.",
    "EXPERIMENT_UNAVAILABLE": "Published evidence is unavailable.",
    "TOOL_NOT_FOUND": "Tool is not registered.",
    "BUDGET_EXCEEDED": "Execution budget is exhausted.",
    "REPAIR_BUDGET_EXCEEDED": "The correction allowance is exhausted.",
    "JOB_ENQUEUE_FAILED": "Job admission failed.",
    "JOB_CANCELLED": "The job was cancelled.",
    "JOB_FAILED": "The job failed.",
    "JOB_LINK_MISMATCH": "Attached job does not match its durable request intent.",
    "PUBLISHED_RESULT_UNVERIFIED": "Completed job publication could not be verified.",
    "REQUEST_CANCELLED": "The request was cancelled.",
    "REQUEST_FAILED": "The request failed.",
    "PROVIDER_ERROR": "The provider request failed.",
    "PROVIDER_DISABLED": "The provider is disabled.",
    "SYNTHETIC_FAILURE": "The job failed.",
    "FAILED": "The request failed.",
    "CANCELLED": "The request was cancelled.",
    "COMPLETED": "The request completed.",
    "SESSION_REQUIRED": "Session authority is required.",
}
_PUBLIC_ERROR_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,47}$")
_LEGACY_PUBLIC_ERROR_MESSAGES = {
    "INVALID_ARGUMENTS": frozenset({
        "Arguments were rejected.",
        "Exactly one of scenario or experiment_id is required.",
    }),
    "UNAUTHORIZED_SESSION": frozenset({
        "Session is not active.",
        "Request-bound enqueue requires fenced admission.",
    }),
}


class PublicToolError(StrictSchema):
    """Bounded public error shape; arbitrary worker fields are ignored."""

    model_config = ConfigDict(strict=True, extra="ignore")
    code: str = Field(min_length=1, max_length=48, pattern=r"^[A-Z][A-Z0-9_]{0,47}$")
    message: str = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def canonicalize_message(self) -> PublicToolError:
        self.message = PUBLIC_ERROR_MESSAGES.get(self.code, "The operation failed.")
        return self


def sanitize_error_input(value: Any) -> str | dict[str, str] | None:
    """Canonicalize legacy strings or public error objects before serialization."""
    if value is None:
        return None
    if isinstance(value, PublicToolError):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        code = value.get("code")
        if not isinstance(code, str) or not _PUBLIC_ERROR_CODE.fullmatch(code):
            code = "EXPERIMENT_UNAVAILABLE"
        message = PUBLIC_ERROR_MESSAGES.get(code, "The operation failed.")
        return {"code": code, "message": message}
    if isinstance(value, str):
        code, separator, raw_message = value.partition(":")
        code = code.strip()
        if separator and _PUBLIC_ERROR_CODE.fullmatch(code) and code in PUBLIC_ERROR_MESSAGES:
            message = raw_message.strip()
            variants = _LEGACY_PUBLIC_ERROR_MESSAGES.get(code, frozenset({PUBLIC_ERROR_MESSAGES[code]}))
            if message in variants:
                return f"{code}: {message}"
            return f"{code}: {PUBLIC_ERROR_MESSAGES[code]}"
        lowered = value.lower()
        if "unsupported" in lowered:
            code = "UNSUPPORTED_PARAMETER"
        elif "exactly one" in lowered:
            code = "INVALID_ARGUMENTS"
        else:
            code = "EXPERIMENT_UNAVAILABLE"
        return f"{code}: {PUBLIC_ERROR_MESSAGES[code]}"
    return f"EXPERIMENT_UNAVAILABLE: {PUBLIC_ERROR_MESSAGES['EXPERIMENT_UNAVAILABLE']}"


SafeIdentifier = Annotated[
    str,
    StringConstraints(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$"),
]
ScenarioName = Literal["mcar_0_00", "mcar_0_10", "mcar_0_30", "history_block_0_50"]
PredictorName = Literal["logistic_regression", "random_forest"]
CalibrationMethod = Literal[
    "raw",
    "source_temperature",
    "source_remasked_temperature",
    "source_fraction_binned_temperature",
    "target_temperature",
    "target_platt_logodds",
    "target_beta",
    "target_isotonic",
]
LabelBudget = Literal[0, 25, 50, 100, 200]


# ---------------------------------------------------------------------------
# Provider Message & Tool Call Models
# ---------------------------------------------------------------------------

class FunctionCall(StrictSchema):
    name: str = Field(description="Name of the function called by the provider")
    arguments: str = Field(description="JSON string of function arguments")


class ToolCall(StrictSchema):
    id: str = Field(description="Original provider tool call identifier")
    type: Literal["function"] = "function"
    function: FunctionCall


class AgentMessage(StrictSchema):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[ToolCall] | None = None


# ---------------------------------------------------------------------------
# The Twelve Tool Parameter Schemas
# ---------------------------------------------------------------------------

class InspectDatasetParams(StrictSchema):
    dataset_id: SafeIdentifier = Field(default="bank", description="Dataset identifier; only 'bank' is available")


class ListAvailableScenariosParams(StrictSchema):
    dataset_id: SafeIdentifier = Field(default="bank", description="Dataset identifier; only 'bank' is available")


class InspectMissingnessParams(StrictSchema):
    scenario: ScenarioName | None = Field(default=None, description="Approved development scenario")
    experiment_id: SafeIdentifier | None = Field(default=None, description="Authorized published experiment identifier")

    @model_validator(mode="after")
    def validate_single_selector(self) -> InspectMissingnessParams:
        has_scenario = self.scenario is not None and len(self.scenario.strip()) > 0
        has_exp = self.experiment_id is not None and len(self.experiment_id.strip()) > 0
        if has_scenario == has_exp:
            raise ValueError("Exactly one of 'scenario' or 'experiment_id' must be specified")
        return self


class RunExperimentParams(StrictSchema):
    preset_name: Literal["bank-baseline", "bank-stress", "bank-outage-50"] = Field(
        description="Approved preset name"
    )


class RunStressSuiteParams(StrictSchema):
    suite_name: Literal["bank-stress", "bank-stress-30", "flagship-stress"] = Field(
        description="Approved stress suite alias"
    )


class CompareOutagesParams(StrictSchema):
    experiment_id: SafeIdentifier = Field(description="Authorized published experiment identifier")
    predictor: PredictorName = Field(default="logistic_regression", description="Approved predictor")
    budget: LabelBudget = Field(default=50, description="Supported evaluation label budget")

    @field_validator("budget", mode="before")
    @classmethod
    def require_integer_budget(cls, value: Any) -> Any:
        if type(value) is not int:
            raise ValueError("Budget must be an integer")
        return value


class CompareCalibratorsParams(StrictSchema):
    experiment_id: SafeIdentifier = Field(description="Authorized published experiment identifier")
    scenario: ScenarioName = Field(description="Approved development scenario")
    predictor: PredictorName = Field(default="logistic_regression", description="Approved predictor")
    budget: LabelBudget = Field(default=50, description="Supported evaluation label budget")

    @field_validator("budget", mode="before")
    @classmethod
    def require_integer_budget(cls, value: Any) -> Any:
        if type(value) is not int:
            raise ValueError("Budget must be an integer")
        return value


class GetLabelBudgetCurveParams(StrictSchema):
    experiment_id: SafeIdentifier = Field(description="Authorized published experiment identifier")
    scenario: ScenarioName = Field(description="Approved development scenario")
    predictor: PredictorName = Field(default="logistic_regression", description="Approved predictor")
    method: CalibrationMethod = Field(default="source_fraction_binned_temperature", description="Approved calibration method")
    metric: Literal["brier_score", "log_loss"] = Field(default="brier_score", description="Supported metric")


class CalculateDecisionLossParams(StrictSchema):
    experiment_id: SafeIdentifier = Field(description="Authorized published experiment identifier")
    scenario: ScenarioName = Field(description="Approved development scenario")
    predictor: PredictorName = Field(default="logistic_regression", description="Approved predictor")
    method: CalibrationMethod = Field(default="source_fraction_binned_temperature", description="Approved calibration method")
    fp_cost: float = Field(description="False positive operating cost", allow_inf_nan=False, ge=0, le=100000)
    fn_cost: float = Field(description="False negative operating cost", allow_inf_nan=False, ge=0, le=100000)


class ReadExperimentResultsParams(StrictSchema):
    experiment_id: SafeIdentifier = Field(description="Authorized published experiment identifier")
    condition_key: SafeIdentifier | None = Field(default=None, description="Optional safe condition key to filter")


class GetExperimentMetadataParams(StrictSchema):
    experiment_id: SafeIdentifier = Field(description="Authorized published experiment identifier")


class GenerateResultSummaryParams(StrictSchema):
    experiment_id: SafeIdentifier = Field(description="Authorized published experiment identifier")
    focus: Literal["all", "fallback", "outages", "calibration"] = Field(
        default="all", description="Summary focus"
    )


class ExplanationPlan(StrictSchema):
    """Provider-selected presentation template and references to Python-built facts."""

    template: Literal["summary", "comparisons", "failures", "fallbacks", "costs"]
    condition_refs: list[SafeIdentifier] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def require_unique_references(self) -> ExplanationPlan:
        if len(set(self.condition_refs)) != len(self.condition_refs):
            raise ValueError("condition_refs must be unique")
        return self


# ---------------------------------------------------------------------------
# Tool Result & Trace Schemas
# ---------------------------------------------------------------------------

class ToolResult(StrictSchema):
    tool_name: str
    tool_call_id: str
    status: Literal["success", "error", "unavailable"]
    data: dict[str, Any] | None = None
    error: str | PublicToolError | None = None
    is_side_effect: bool = False
    job_id: str | None = None

    @field_validator("error", mode="before")
    @classmethod
    def sanitize_error(cls, value: Any) -> Any:
        return sanitize_error_input(value)


class ToolTraceEntry(StrictSchema):
    ordinal: int
    tool_name: str
    tool_call_id: str
    arguments: dict[str, Any]
    status: str
    result: dict[str, Any] | None = None
    error: str | PublicToolError | None = None
    job_id: str | None = None

    @field_validator("error", mode="before")
    @classmethod
    def sanitize_error(cls, value: Any) -> Any:
        return sanitize_error_input(value)


# ---------------------------------------------------------------------------
# Agent API Request & Response Schemas
# ---------------------------------------------------------------------------

class AgentRequestSubmit(StrictSchema):
    prompt: str = Field(min_length=1, max_length=2000, description="Natural language inquiry or command")
    idempotency_key: str = Field(min_length=1, max_length=128, description="Client idempotency key")


class AgentResumeRequest(StrictSchema):
    nonce: str = Field(min_length=1, max_length=64, description="Single-use resume nonce")


class AgentRequestResponse(StrictSchema):
    request_id: str
    session_id: str
    status: str
    prompt: str
    turn_count: int
    call_count: int
    repair_count: int
    active_job_id: str | None = None
    active_tool_call_id: str | None = None
    resume_nonce: str | None = None
    tool_trace: list[ToolTraceEntry] = []
    evidence_refs: list[str] = []
    final_response: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    created_at: str
    updated_at: str


class AgentStatusResponse(StrictSchema):
    enabled: bool
    available: bool
    model: str
    max_turns: int
    max_calls: int
    active_requests_count: int = 0
