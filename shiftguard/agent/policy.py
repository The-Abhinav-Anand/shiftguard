"""Policy rules, bounded limits, and validation allowlists for Gate 6 agent."""

from __future__ import annotations

from typing import Any, NamedTuple


def safe_tool_call_id(value: Any) -> str | None:
    """Accept opaque tool-call IDs with 1 to 256 UTF-8 bytes and no NUL."""
    if not isinstance(value, str) or not value or "\x00" in value:
        return None
    try:
        return value if len(value.encode("utf-8")) <= 256 else None
    except (UnicodeEncodeError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Execution Limits
# ---------------------------------------------------------------------------

MAX_TURNS: int = 6
MAX_TOOL_CALLS: int = 8
MAX_REPAIRS_PER_SIGNATURE: int = 1
MAX_PROMPT_LENGTH: int = 2000
DEFAULT_LEASE_SECONDS: int = 60

# ---------------------------------------------------------------------------
# Allowlisted Scientific Entities & Parameters
# ---------------------------------------------------------------------------

APPROVED_DATASETS: frozenset[str] = frozenset({"bank"})

APPROVED_PRESETS: frozenset[str] = frozenset({
    "bank-baseline",
    "bank-stress",
    "bank-outage-50",
})

APPROVED_STRESS_SUITES: frozenset[str] = frozenset({
    "bank-stress",
    "bank-stress-30",
    "flagship-stress",
})

APPROVED_PREDICTORS: frozenset[str] = frozenset({
    "logistic_regression",
    "random_forest",
})

APPROVED_SCENARIOS: frozenset[str] = frozenset({
    "mcar_0_00",
    "mcar_0_10",
    "mcar_0_30",
    "history_block_0_50",
})

APPROVED_BUDGETS: frozenset[int] = frozenset({0, 25, 50, 100, 200})

APPROVED_METRICS: frozenset[str] = frozenset({
    "brier_score",
    "log_loss",
})

APPROVED_CALIBRATORS: frozenset[str] = frozenset({
    "source_fraction_binned_temperature",
    "target_temperature",
    "source_temperature",
    "source_remasked_temperature",
    "target_platt_logodds",
    "target_beta",
    "target_isotonic",
    "raw",
})

APPROVED_METHODS: frozenset[str] = frozenset({
    "raw",
    "source_temperature",
    "source_remasked_temperature",
    "source_fraction_binned_temperature",
    "target_temperature",
    "target_platt_logodds",
    "target_beta",
    "target_isotonic",
})

APPROVED_FOCUSES: frozenset[str] = frozenset({
    "all",
    "fallback",
    "outages",
    "calibration",
})

# Supported operating cost pairs persisted in decision loss curves
SUPPORTED_COST_PAIRS: frozenset[tuple[float, float]] = frozenset({
    (1.0, 1.0),
    (1.0, 4.0),
    (4.0, 1.0),
    (1.0, 9.0),
    (9.0, 1.0),
})

# Bank features: exactly the ten modeled features from the frozen Bank dataset contract
BANK_MODELED_FEATURES: tuple[str, ...] = (
    "age",
    "job",
    "marital",
    "education",
    "default",
    "housing",
    "loan",
    "pdays",
    "previous",
    "poutcome",
)

# ---------------------------------------------------------------------------
# Error Codes
# ---------------------------------------------------------------------------

class AgentErrorCode:
    TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
    INVALID_ARGUMENTS = "INVALID_ARGUMENTS"
    UNAUTHORIZED_SESSION = "UNAUTHORIZED_SESSION"
    EXECUTION_NOT_AUTHORIZED = "EXECUTION_NOT_AUTHORIZED"
    UNAUTHORIZED_EXPERIMENT_REFERENCE = "UNAUTHORIZED_EXPERIMENT_REFERENCE"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    REPAIR_BUDGET_EXCEEDED = "REPAIR_BUDGET_EXCEEDED"
    JOB_ENQUEUE_FAILED = "JOB_ENQUEUE_FAILED"
    UNSUPPORTED_COMBINATION = "UNSUPPORTED_COMBINATION"
    UNSUPPORTED_COST_PAIR = "UNSUPPORTED_COST_PAIR"
    UNSUPPORTED_PARAMETER = "UNSUPPORTED_PARAMETER"
    EXPERIMENT_NOT_FOUND = "EXPERIMENT_NOT_FOUND"
    EXPERIMENT_UNAVAILABLE = "EXPERIMENT_UNAVAILABLE"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    PROVIDER_DISABLED = "PROVIDER_DISABLED"
    SESSION_REQUIRED = "SESSION_REQUIRED"
    REQUEST_CANCELLED = "REQUEST_CANCELLED"
    REQUEST_FAILED = "REQUEST_FAILED"


# ---------------------------------------------------------------------------
# Repair Signature Tracking
# ---------------------------------------------------------------------------

class RepairSignature(NamedTuple):
    tool_name: str
    error_type: str


def normalized_repair_signature(tool_name: str, error_code: str, field: str = "") -> str:
    """Return the stable, value-free key used by the one-repair-per-error policy."""
    safe_tool = "".join(ch.lower() for ch in tool_name if ch.isalnum() or ch == "_")[:64]
    safe_code = "".join(ch.upper() for ch in error_code if ch.isalnum() or ch == "_")[:48]
    safe_field = "".join(ch.lower() for ch in field if ch.isalnum() or ch == "_")[:64]
    return f"{safe_tool}:{safe_code}:{safe_field}"


def compute_repair_signature(tool_name: str, error_message: str) -> str:
    """Derive a value-free normalized signature from a bounded public error."""
    first_line = error_message.split("\n", 1)[0].strip()
    parts = first_line.split(":", 2)
    if len(parts) >= 2:
        code = parts[0].strip().split()[0]
        # Public rejection messages carry explanatory text, not a stable field
        # identity. Keep the signature aligned with the controller's pre-check.
        return normalized_repair_signature(tool_name, code)
    return normalized_repair_signature(tool_name, first_line[:48].strip(), "")
