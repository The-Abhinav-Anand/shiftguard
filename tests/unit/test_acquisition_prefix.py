from __future__ import annotations

from shiftguard.protocol.acquisition import LabelBlindTargetProvider


def test_target_provider_order_is_label_blind_and_prefix_nested() -> None:
    rows = tuple({"row_id": index, "age": "30", "y": index % 2} for index in range(1, 11))
    relabeled = tuple({**row, "y": 1 - int(row["y"])} for row in rows)
    first = LabelBlindTargetProvider(rows, seed=31)
    second = LabelBlindTargetProvider(relabeled, seed=31)

    assert first.order == second.order
    assert first.pool_record_ids == tuple(range(1, 11))
    assert first.pool_features == second.pool_features
    assert all("y" not in row for row in first.pool_features)
    assert first.reveal_prefix(3).record_ids == first.reveal_prefix(6).record_ids[:3]
    assert all("y" not in row for row in first.reveal_prefix(3).features)
    assert not hasattr(first, "labels")
