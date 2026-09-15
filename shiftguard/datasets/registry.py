from __future__ import annotations

import numpy as np


def select_nested_prefix(row_ids: tuple[int, ...], seed: int, count: int) -> tuple[int, ...]:
    if count < 0 or count > len(row_ids):
        raise ValueError("acquisition count must be within the available row IDs")
    ordered = np.random.default_rng(seed).permutation(row_ids)
    return tuple(int(row_id) for row_id in ordered[:count])
