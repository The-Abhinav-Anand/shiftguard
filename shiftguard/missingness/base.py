from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from shiftguard.datasets.bank import BANK_FEATURES


def stable_mask_hash(record_ids: tuple[int, ...], features: tuple[str, ...], selected: tuple[bool, ...]) -> str:
    payload = json.dumps({"record_ids": record_ids, "features": features, "selected": selected}, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RawFeatureMask:
    record_ids: tuple[int, ...]
    features: tuple[str, ...]
    selected: tuple[bool, ...]
    requested_row_probability: float

    @property
    def mask_id(self) -> str:
        return stable_mask_hash(self.record_ids, self.features, self.selected)

    def apply(self, rows: tuple[dict[str, str | int], ...]) -> tuple[dict[str, str | int | None], ...]:
        by_id = dict(zip(self.record_ids, self.selected, strict=True))
        transformed = []
        for row in rows:
            copy = dict(row)
            if by_id[int(row["row_id"])]:
                for feature in self.features:
                    copy[feature] = None
            transformed.append(copy)
        return tuple(transformed)

    def rates(self, rows: tuple[dict[str, str | int], ...]) -> dict[str, float | int]:
        selected = dict(zip(self.record_ids, self.selected, strict=True))
        observed_all = observed_history = newly_missing = rows_newly_missing = 0
        natural_inside_history = natural_outside_history = 0
        all_cells = len(rows) * len(BANK_FEATURES)
        for row in rows:
            newly_missing_for_row = False
            for feature in BANK_FEATURES:
                observed = row[feature] not in (None, "")
                if observed:
                    observed_all += 1
                elif feature in self.features:
                    natural_inside_history += 1
                else:
                    natural_outside_history += 1
                if feature in self.features and observed:
                    observed_history += 1
                    if selected[int(row["row_id"])]:
                        newly_missing += 1
                        newly_missing_for_row = True
            rows_newly_missing += int(newly_missing_for_row)
        selected_rows = sum(selected[int(row["row_id"])] for row in rows)
        return {
            "requested_row_probability": self.requested_row_probability,
            "realized_selected_row_fraction": selected_rows / len(rows) if rows else 0.0,
            "row_count": len(rows),
            "selected_rows": selected_rows,
            "rows_with_new_missingness": rows_newly_missing,
            "rows_with_new_missingness_fraction": rows_newly_missing / len(rows) if rows else 0.0,
            "newly_missing_cells": newly_missing,
            "observed_all_feature_cells": observed_all,
            "observed_history_eligible_cells": observed_history,
            "observed_history_group_new_missing_rate": newly_missing / observed_history if observed_history else 0.0,
            "observed_all_feature_cells_new_missing_rate": newly_missing / observed_all if observed_all else 0.0,
            "all_feature_cells": all_cells,
            "natural_missing_inside_history_cells": natural_inside_history,
            "natural_missing_outside_history_cells": natural_outside_history,
            "natural_missing_cells": natural_inside_history + natural_outside_history,
            "total_missing_cells": natural_inside_history + natural_outside_history + newly_missing,
            "total_missing_rate_over_all_feature_cells": (natural_inside_history + natural_outside_history + newly_missing) / all_cells if all_cells else 0.0,
        }
