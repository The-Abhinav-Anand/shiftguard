from __future__ import annotations

from collections.abc import Iterable

from sklearn.model_selection import train_test_split


ROLE_FRACTIONS = {"train": 0.55, "source_cal": 0.15, "target_pool": 0.10, "final_test": 0.20}


def make_role_splits(rows: Iterable[dict[str, object]], split_seed: int) -> dict[str, tuple[int, ...]]:
    ids = [int(row["row_id"]) for row in rows]
    labels = [int(row["y"]) for row in rows]
    train_ids, holdout_ids, _train_y, holdout_y = train_test_split(
        ids, labels, test_size=0.45, stratify=labels, random_state=split_seed,
    )
    source_ids, remaining_ids, _source_y, remaining_y = train_test_split(
        holdout_ids, holdout_y, test_size=2 / 3, stratify=holdout_y, random_state=split_seed + 1,
    )
    pool_ids, final_ids = train_test_split(
        remaining_ids, test_size=2 / 3, stratify=remaining_y, random_state=split_seed + 2,
    )
    return {"train": tuple(sorted(train_ids)), "source_cal": tuple(sorted(source_ids)), "target_pool": tuple(sorted(pool_ids)), "final_test": tuple(sorted(final_ids))}
