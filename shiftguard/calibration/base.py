from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ProbabilityMap(Protocol):
    def predict_proba(self, features): ...


@dataclass(frozen=True)
class CalibrationRecord:
    requested_method: str
    resolved_method: str
    fit_status: str
    fallback_reason: str | None
    labels_consumed: int
    fitted_temperature: float | None
