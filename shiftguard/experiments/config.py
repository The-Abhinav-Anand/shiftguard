from __future__ import annotations

from dataclasses import dataclass, field
import json
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
