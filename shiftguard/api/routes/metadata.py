"""Approved metadata endpoints for datasets, models, and scenarios (presets only)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v1", tags=["metadata"])

APPROVED_DATASETS = {
    "bank": {
        "id": "bank",
        "name": "Bank Marketing Dataset (Moro et al., 2014)",
        "source": "UCI Machine Learning Repository",
        "features_count": 16,
        "records_count": 41188,
        "evaluation_partition_size": 8238,
        "task": "binary_classification",
        "description": "Direct marketing campaigns (phone calls) of a Portuguese banking institution.",
    },
    "adult_train": {
        "id": "adult_train",
        "name": "Adult Census Income Dataset (Development Train-Only Ownership)",
        "source": "UCI Machine Learning Repository",
        "features_count": 13,
        "records_count": 32561,
        "task": "binary_classification",
        "confirmatory_test_sealed": True,
        "description": "Adult training dataset owned for development validation; test file sealed.",
    },
}

APPROVED_MODELS = [
    {
        "id": "logistic_regression",
        "name": "Logistic Regression (L2 regularized)",
        "solver": "liblinear",
        "penalty": "l2",
        "c_param": 1.0,
        "deterministic": True,
    },
    {
        "id": "random_forest",
        "name": "Random Forest Classifier",
        "n_estimators": 100,
        "max_depth": 10,
        "min_samples_leaf": 5,
        "n_jobs": 1,
        "deterministic": True,
    },
]

APPROVED_SCENARIOS = [
    {
        "id": "baseline",
        "description": "No synthetic missingness injected on target features.",
    },
    {
        "id": "outage",
        "description": "Complete outage of historical feature group during test window.",
    },
    {
        "id": "history_block_0_50",
        "description": "Historical group block missingness at 50% probability.",
    },
    {
        "id": "mcar_matched_history",
        "description": "Cellwise MCAR missingness matched to realized history block rate.",
    },
    {
        "id": "mcar_0_10",
        "description": "Uniform MCAR missingness at 10% rate.",
    },
    {
        "id": "mcar_0_30",
        "description": "Uniform MCAR missingness at 30% rate (strictly nesting 10% mask).",
    },
]


@router.get("/datasets")
def list_datasets() -> dict[str, list[dict]]:
    """List approved dataset metadata (no raw rows or labels)."""
    return {"datasets": list(APPROVED_DATASETS.values())}


@router.get("/datasets/{dataset_id}")
def get_dataset(dataset_id: str) -> dict:
    """Get metadata for a specific approved dataset."""
    if dataset_id not in APPROVED_DATASETS:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "DATASET_NOT_FOUND",
                    "message": f"Dataset '{dataset_id}' not found in approved registry",
                }
            },
        )
    return APPROVED_DATASETS[dataset_id]


@router.get("/models")
def list_models() -> dict[str, list[dict]]:
    """List approved prediction models."""
    return {"models": APPROVED_MODELS}


@router.get("/scenarios")
def list_scenarios() -> dict[str, list[dict]]:
    """List approved shift and missingness scenarios."""
    return {"scenarios": APPROVED_SCENARIOS}
