from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class AcquiredTargetLabels:
    record_ids: tuple[int, ...]
    features: tuple[dict[str, str | int], ...]
    labels: tuple[int, ...]


class LabelBlindTargetProvider:
    def __init__(self, rows: tuple[dict[str, str | int], ...], seed: int, target_column: str = "y") -> None:
        self._rows = {int(row["row_id"]): row for row in rows}
        self.target_column = target_column
        self.pool_record_ids = tuple(sorted(self._rows))
        self.pool_features = tuple(
            {key: value for key, value in self._rows[row_id].items() if key != self.target_column}
            for row_id in self.pool_record_ids
        )
        self.order = tuple(int(value) for value in np.random.default_rng(seed).permutation(sorted(self._rows)))
        self.seed = seed

    def reveal_prefix(self, count: int) -> AcquiredTargetLabels:
        if count < 0 or count > len(self.order):
            raise ValueError("requested target prefix is outside the target pool")
        ids = self.order[:count]
        rows = tuple(self._rows[row_id] for row_id in ids)
        return AcquiredTargetLabels(
            ids,
            tuple({key: value for key, value in row.items() if key != self.target_column} for row in rows),
            tuple(int(row[self.target_column]) for row in rows),
        )
