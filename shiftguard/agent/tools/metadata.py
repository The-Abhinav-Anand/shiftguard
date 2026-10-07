"""Metadata tool handlers: inspect_dataset, list_available_scenarios, inspect_missingness."""

from __future__ import annotations

import math
from typing import Any

from shiftguard.agent.policy import (
    APPROVED_DATASETS,
    APPROVED_SCENARIOS,
    APPROVED_PRESETS,
    APPROVED_PREDICTORS,
    BANK_MODELED_FEATURES,
    AgentErrorCode,
)
from shiftguard.agent.schemas import (
    InspectDatasetParams,
    InspectMissingnessParams,
    ListAvailableScenariosParams,
    ToolResult,
)
from shiftguard.agent.tools import ToolContext, experiment_evidence_allowed
from shiftguard.datasets.bank import (
    BANK_FEATURES,
    FROZEN_BANK_SOURCE,
    FROZEN_CLEAN_DIGEST,
    FROZEN_ROW_COUNT,
    TARGET_COLUMN,
)
from shiftguard.storage.repositories import ExperimentRepository


_MASK_RATE_FIELDS = frozenset({
    "requested_row_probability", "requested_rate", "realized_selected_row_fraction",
    "row_count", "selected_rows", "rows_with_new_missingness",
    "rows_with_new_missingness_fraction", "newly_missing_cells",
    "observed_all_feature_cells", "observed_history_eligible_cells",
    "observed_eligible_cells", "observed_history_group_new_missing_rate",
    "observed_all_feature_cells_new_missing_rate",
    "observed_eligible_cells_new_missing_rate", "all_feature_cells",
    "natural_missing_inside_history_cells", "natural_missing_outside_history_cells",
    "natural_missing_cells", "total_missing_cells", "total_missing_rate_over_all_feature_cells",
})


def _project_mask_rates(raw: Any) -> dict[str, int | float]:
    if not isinstance(raw, dict):
        return {}
    projected = {}
    for key, value in raw.items():
        if key not in _MASK_RATE_FIELDS or isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if isinstance(value, float) and not math.isfinite(value):
            continue
        projected[key] = value
    return projected


def _project_masks(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    allowed_prefixes = set(APPROVED_SCENARIOS) | {"mcar_matched", "history_block"}
    projected: dict[str, Any] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        if key in {"full_pool", "acquired_subset", "test"}:
            item = {}
            for id_key in ("mask_id", "parent_mask_id"):
                ident = value.get(id_key)
                if isinstance(ident, str) and len(ident) <= 128 and ident.replace("-", "").isalnum():
                    item[id_key] = ident
            item["rates"] = _project_mask_rates(value.get("rates"))
            projected[key] = item
            continue
        prefix = next((p for p in allowed_prefixes if key.startswith(p + "_")), None)
        if not prefix:
            continue
        if key.endswith("_rates"):
            projected[key] = _project_mask_rates(value)
    for key, value in raw.items():
        if not isinstance(key, str):
            continue
        prefix = next((p for p in allowed_prefixes if key.startswith(p + "_")), None)
        if prefix and key.endswith("_mask_id") and isinstance(value, str) and len(value) <= 128 and value.replace("-", "").isalnum():
            projected[key] = value
    return projected


def inspect_dataset(params: InspectDatasetParams, ctx: ToolContext, tool_call_id: str) -> ToolResult:
    """Inspect dataset metadata, features, and natural missingness contract."""
    ds = params.dataset_id.lower().strip()
    if ds not in APPROVED_DATASETS:
        return ToolResult(
            tool_name="inspect_dataset",
            tool_call_id=tool_call_id,
            status="unavailable",
            error=f"Dataset '{params.dataset_id}' is unsupported. Only approved dataset is 'bank'. Adult/MAR confirmatory datasets remain sealed.",
        )

    data = {
        "dataset_id": "bank",
        "name": "Bank Marketing (UCI 222)",
        "row_count": FROZEN_ROW_COUNT,
        "modeled_features": list(BANK_FEATURES),
        "target_column": TARGET_COLUMN,
        "natural_missingness_rate": 0.0,
        "clean_sha256": FROZEN_CLEAN_DIGEST,
        "source_citation": FROZEN_BANK_SOURCE.get("citation"),
        "license": FROZEN_BANK_SOURCE.get("license"),
        "evaluation_tier": "development",
        "notes": "Bank clean CSV schema has complete values across the 10 modeled features. Missingness is injected experimentally.",
    }
    return ToolResult(
        tool_name="inspect_dataset",
        tool_call_id=tool_call_id,
        status="success",
        data=data,
    )


def list_available_scenarios(params: ListAvailableScenariosParams, ctx: ToolContext, tool_call_id: str) -> ToolResult:
    """List executable development scenarios, approved presets, and allowed parameters."""
    ds = params.dataset_id.lower().strip()
    if ds not in APPROVED_DATASETS:
        return ToolResult(
            tool_name="list_available_scenarios",
            tool_call_id=tool_call_id,
            status="unavailable",
            error=f"Dataset '{params.dataset_id}' is unsupported. Development scenarios exist only for 'bank'.",
        )

    data = {
        "dataset_id": "bank",
        "approved_presets": sorted(list(APPROVED_PRESETS)),
        "approved_scenarios": [
            {"id": "mcar_0_00", "type": "none", "rate": 0.00, "description": "Baseline full observation"},
            {"id": "mcar_0_10", "type": "MCAR", "rate": 0.10, "description": "10% cellwise completely at random missingness"},
            {"id": "mcar_0_30", "type": "MCAR", "rate": 0.30, "description": "30% cellwise completely at random missingness"},
            {"id": "history_block_0_50", "type": "block_outage", "rate": 0.50, "description": "History feature group block outage on 50% rows"},
        ],
        "supported_predictors": sorted(list(APPROVED_PREDICTORS)),
        "supported_budgets": [0, 25, 50, 100, 200],
        "supported_cost_pairs": [[1.0, 1.0], [1.0, 4.0], [1.0, 9.0], [4.0, 1.0], [9.0, 1.0]],
        "master_seed": 31001,
        "protocol_id": "sg-protocol-1.0-draft-gate3",
    }
    return ToolResult(
        tool_name="list_available_scenarios",
        tool_call_id=tool_call_id,
        status="success",
        data=data,
    )


def inspect_missingness(params: InspectMissingnessParams, ctx: ToolContext, tool_call_id: str) -> ToolResult:
    """Inspect missingness injection parameters or realized rates from a published experiment."""
    if params.scenario:
        scenario = params.scenario.strip().lower()
        known_scenarios = {
            "mcar_0_00": {"pattern": "none", "requested_cell_rate": 0.00, "description": "Baseline full observation"},
            "mcar_0_10": {"pattern": "mcar", "requested_cell_rate": 0.10, "description": "10% cellwise uniform missingness"},
            "mcar_0_30": {"pattern": "mcar", "requested_cell_rate": 0.30, "description": "30% cellwise uniform missingness"},
            "history_block_0_50": {"pattern": "block_outage", "row_probability": 0.50, "affected_features": ["pdays", "previous", "poutcome"]},
        }
        if scenario not in known_scenarios:
            return ToolResult(
                tool_name="inspect_missingness",
                tool_call_id=tool_call_id,
                status="error",
                error=f"Scenario '{params.scenario}' is not recognized. Approved development scenarios: {list(known_scenarios.keys())}",
            )
        data = {
            "scenario": scenario,
            **known_scenarios[scenario],
            "notes": "Unexecuted scenario parameters define requested injection probabilities. To inspect realized cell counts and empirical row fractions, pass experiment_id.",
        }
        return ToolResult(
            tool_name="inspect_missingness",
            tool_call_id=tool_call_id,
            status="success",
            data=data,
        )

    if params.experiment_id:
        exp_id = params.experiment_id.strip()
        if not experiment_evidence_allowed(ctx, exp_id):
            return ToolResult(
                tool_name="inspect_missingness",
                tool_call_id=tool_call_id,
                status="unavailable",
                error=f"{AgentErrorCode.UNAUTHORIZED_EXPERIMENT_REFERENCE}: Experiment reference is not authorized for this request.",
            )
        repo = ExperimentRepository(ctx.engine)
        published = repo.get_published(exp_id)
        if not published:
            return ToolResult(
                tool_name="inspect_missingness",
                tool_call_id=tool_call_id,
                status="error",
                error=f"Experiment '{params.experiment_id}' was not found among verified PUBLISHED records.",
            )
        stored_exp, pub_rec = published
        payload = getattr(stored_exp, "deterministic_payload", None) or getattr(stored_exp, "payload_json", {})
        masks = _project_masks(payload.get("masks", {}))
        data = {
            "experiment_id": getattr(stored_exp, "experiment_id", getattr(stored_exp, "id", "")),
            "created_at": pub_rec.created_at,
            "realized_mask_summaries": masks,
            "notes": "Realized mask summaries report observed row fractions and total missing cell rates computed during this execution.",
        }
        return ToolResult(
            tool_name="inspect_missingness",
            tool_call_id=tool_call_id,
            status="success",
            data=data,
        )

    return ToolResult(
        tool_name="inspect_missingness",
        tool_call_id=tool_call_id,
        status="error",
        error="Exactly one of 'scenario' or 'experiment_id' must be specified.",
    )
