from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from pathlib import Path

import yaml

from shiftguard.datasets.bank import BANK_FEATURES
from shiftguard.protocol.splits import ROLE_FRACTIONS


DEVELOPMENT_SEEDS = (31001, 31002, 31003)
CONFIRMATORY_SEEDS = (41001, 41002, 41003)


@dataclass(frozen=True)
class BaselineConfig:
    master_seed: int
    features: tuple[str, ...] = BANK_FEATURES
    role_fractions: dict[str, float] = field(default_factory=lambda: dict(ROLE_FRACTIONS))
    artifact_root: Path = Path("var/artifacts")
    dataset_csv: Path = Path("var/datasets/bank-additional-full.csv")
    dataset_manifest: Path = Path("var/datasets/bank-marketing.manifest.json")
    protocol_id: str = "sg-protocol-1.0-draft"
    evaluation_tier: str = "development"

    def __post_init__(self) -> None:
        if self.features != BANK_FEATURES:
            raise ValueError("Gate1 features must match the frozen Bank feature list")
        if self.role_fractions != ROLE_FRACTIONS:
            raise ValueError("Gate1 role fractions must match the frozen protocol")
        if self.evaluation_tier != "development":
            raise ValueError("confirmatory execution is forbidden until sg-protocol-1.0 is locked")
        if self.master_seed not in DEVELOPMENT_SEEDS:
            raise ValueError("master_seed must belong to the declared development seed set")

    def to_dict(self) -> dict[str, object]:
        return {"master_seed": self.master_seed, "features": list(self.features), "role_fractions": self.role_fractions, "protocol_id": self.protocol_id, "evaluation_tier": self.evaluation_tier, "dataset_csv": str(self.dataset_csv), "dataset_manifest": str(self.dataset_manifest)}


def load_baseline_config(path: Path) -> BaselineConfig:
    if path.suffix in {".yaml", ".yml"}:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Gate1 configuration must be a mapping")
    allowed = {"master_seed", "features", "role_fractions", "artifact_root", "dataset_csv", "dataset_manifest", "protocol_id", "evaluation_tier"}
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError(f"unknown Gate1 configuration keys: {sorted(unknown)}")
    for key in ("artifact_root", "dataset_csv", "dataset_manifest"):
        if key in payload:
            payload[key] = Path(payload[key])
    if "features" in payload:
        payload["features"] = tuple(payload["features"])
    return BaselineConfig(**payload)


@dataclass(frozen=True)
class OutageConfig(BaselineConfig):
    run_type: str = "outage_recovery"
    history_row_probability: float = 0.5
    target_label_budget: int = 50
    source_calibrator: str = "source_temperature"
    target_calibrator: str = "target_temperature"

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.run_type != "outage_recovery":
            raise ValueError("Gate2 run_type must be outage_recovery")
        if self.history_row_probability != 0.5:
            raise ValueError("Gate2 history row probability is frozen at 0.5")
        if self.target_label_budget != 50:
            raise ValueError("Gate2 target label budget is frozen at 50")
        if (self.source_calibrator, self.target_calibrator) != ("source_temperature", "target_temperature"):
            raise ValueError("Gate2 calibrators are frozen to source and target temperature")

    def to_dict(self) -> dict[str, object]:
        return {**super().to_dict(), "run_type": self.run_type, "history_row_probability": self.history_row_probability, "target_label_budget": self.target_label_budget, "source_calibrator": self.source_calibrator, "target_calibrator": self.target_calibrator}


SUPPORTED_PREDICTORS = ("logistic_regression", "random_forest")
SUPPORTED_BUDGETS = (0, 25, 50, 100, 200)
SUPPORTED_CALIBRATION_METHODS = (
    "raw",
    "source_temperature",
    "source_remasked_temperature",
    "source_fraction_binned_temperature",
    "target_temperature",
    "target_platt_logodds",
    "target_beta",
    "target_isotonic",
)


@dataclass(frozen=True)
class StressConfig(BaselineConfig):
    run_type: str = "stress_engine"
    predictors: tuple[str, ...] = ("logistic_regression", "random_forest")
    budgets: tuple[int, ...] = (0, 25, 50, 100, 200)
    mcar_rates: tuple[float, ...] = (0.00, 0.10, 0.30)
    history_row_probability: float = 0.50
    calibration_methods: tuple[str, ...] = SUPPORTED_CALIBRATION_METHODS
    cost_grid: tuple[tuple[float, float], ...] = (
        (1.0, 1.0),
        (1.0, 4.0),
        (1.0, 9.0),
        (4.0, 1.0),
        (9.0, 1.0),
    )
    protocol_id: str = "sg-protocol-1.0-draft-gate3"

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.run_type != "stress_engine":
            raise ValueError("Gate3 run_type must be stress_engine")
        if not self.predictors:
            raise ValueError("predictors must not be empty")
        for p in self.predictors:
            if p not in SUPPORTED_PREDICTORS:
                raise ValueError(f"unsupported predictor: {p}")
        if not self.budgets:
            raise ValueError("budgets must not be empty")
        for b in self.budgets:
            if b not in SUPPORTED_BUDGETS:
                raise ValueError(f"unsupported budget: {b}")
        if 50 not in self.budgets:
            raise ValueError("budgets must include budget 50 required for pattern-vs-rate comparison")
        if not self.mcar_rates:
            raise ValueError("mcar_rates must not be empty")
        formatted_names: set[str] = set()
        for r in self.mcar_rates:
            if not (math.isfinite(r) and 0.0 <= r < 1.0):
                raise ValueError(f"invalid mcar_rate: {r}")
            if r == 0.0:
                continue
            name = f"mcar_{r:.2f}".replace(".", "_") if math.isclose(r, round(r, 2), abs_tol=1e-5) else f"mcar_{str(r).replace('.', '_')}"
            if name in formatted_names or name in ("baseline", "history_block_0_50", "mcar_matched_history"):
                raise ValueError(f"MCAR rate collision detected in configuration: {r} maps to '{name}'")
            formatted_names.add(name)
        if not self.calibration_methods:
            raise ValueError("calibration_methods must not be empty")
        for m in self.calibration_methods:
            if m not in SUPPORTED_CALIBRATION_METHODS:
                raise ValueError(f"unsupported calibration method: {m}")
        if not self.cost_grid:
            raise ValueError("cost_grid must not be empty")
        has_0_5_thresh = False
        for item in self.cost_grid:
            if len(item) != 2:
                raise ValueError(f"each cost_grid entry must have length 2, got {item}")
            fp, fn = float(item[0]), float(item[1])
            if not (math.isfinite(fp) and math.isfinite(fn) and fp > 0 and fn > 0):
                raise ValueError(f"cost_grid items must be positive finite floats, got {(fp, fn)}")
            if math.isclose(fp / (fp + fn), 0.5, abs_tol=1e-3):
                has_0_5_thresh = True
        if not has_0_5_thresh:
            raise ValueError("cost_grid must include at least one cost pair with threshold 0.5 (equal FP and FN costs)")

    def to_dict(self) -> dict[str, object]:
        return {
            **super().to_dict(),
            "run_type": self.run_type,
            "predictors": list(self.predictors),
            "budgets": list(self.budgets),
            "mcar_rates": list(self.mcar_rates),
            "history_row_probability": self.history_row_probability,
            "calibration_methods": list(self.calibration_methods),
            "cost_grid": [list(item) for item in self.cost_grid],
        }


def load_stress_config(path: Path) -> StressConfig:
    if path.suffix in {".yaml", ".yml"}:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Gate3 configuration must be a mapping")
    allowed = {
        "master_seed", "features", "role_fractions", "artifact_root", "dataset_csv",
        "dataset_manifest", "protocol_id", "evaluation_tier", "run_type", "predictors",
        "budgets", "mcar_rates", "history_row_probability", "calibration_methods", "cost_grid",
    }
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError(f"unknown Gate3 configuration keys: {sorted(unknown)}")
    for key in ("artifact_root", "dataset_csv", "dataset_manifest"):
        if key in payload:
            payload[key] = Path(payload[key])
    if "features" in payload:
        payload["features"] = tuple(payload["features"])
    if "predictors" in payload:
        payload["predictors"] = tuple(payload["predictors"])
    if "budgets" in payload:
        payload["budgets"] = tuple(payload["budgets"])
    if "mcar_rates" in payload:
        payload["mcar_rates"] = tuple(payload["mcar_rates"])
    if "calibration_methods" in payload:
        payload["calibration_methods"] = tuple(payload["calibration_methods"])
    if "cost_grid" in payload:
        payload["cost_grid"] = tuple((float(pair[0]), float(pair[1])) for pair in payload["cost_grid"])
    return StressConfig(**payload)


def load_run_config(path: Path) -> BaselineConfig | OutageConfig | StressConfig:
    if path.suffix in {".yaml", ".yml"}:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Gate configuration must be a mapping")
    run_type = payload.get("run_type")
    if run_type == "adult_confirmatory":
        raise RuntimeError("Adult confirmatory execution is sealed until Gate 8 protocol lock.")
    if run_type == "stress_engine":
        return load_stress_config(path)
    if run_type == "outage_recovery":
        allowed = {"master_seed", "features", "role_fractions", "artifact_root", "dataset_csv", "dataset_manifest", "protocol_id", "evaluation_tier", "run_type", "history_row_probability", "target_label_budget", "source_calibrator", "target_calibrator"}
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"unknown Gate2 configuration keys: {sorted(unknown)}")
        for key in ("artifact_root", "dataset_csv", "dataset_manifest"):
            if key in payload:
                payload[key] = Path(payload[key])
        if "features" in payload:
            payload["features"] = tuple(payload["features"])
        return OutageConfig(**payload)
    return load_baseline_config(path)
