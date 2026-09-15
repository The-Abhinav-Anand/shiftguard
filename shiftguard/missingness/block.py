from __future__ import annotations

import numpy as np

from shiftguard.missingness.base import RawFeatureMask


HISTORY_FEATURES = ("pdays", "previous", "poutcome")


def history_block_mask(record_ids: tuple[int, ...], seed: int, row_probability: float) -> RawFeatureMask:
    if not 0.0 <= row_probability <= 1.0:
        raise ValueError("history row probability must be between zero and one")
    selected = tuple(bool(value < row_probability) for value in np.random.default_rng(seed).random(len(record_ids)))
    return RawFeatureMask(record_ids, HISTORY_FEATURES, selected, row_probability)
