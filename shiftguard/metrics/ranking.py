from __future__ import annotations

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

from shiftguard.metrics.validation import validate_metric_inputs


def ranking_metrics(
    labels: list[int] | tuple[int, ...] | np.ndarray,
    probabilities: list[float] | tuple[float, ...] | np.ndarray,
) -> dict[str, float | None]:
    """Compute AUROC, Average Precision (AP), and prevalence.

    If labels contain fewer than 2 classes or are empty, AUROC and AP return None.
    Average Precision uses sklearn's average_precision_score and is distinct from trapezoidal PR-AUC.
    """
    y_true, y_prob = validate_metric_inputs(labels, probabilities, allow_empty=True)

    if len(y_true) == 0:
        return {"roc_auc": None, "average_precision": None, "prevalence": None}

    prevalence = float(np.mean(y_true))

    if len(np.unique(y_true)) < 2:
        return {"roc_auc": None, "average_precision": None, "prevalence": prevalence}

    try:
        auroc = float(roc_auc_score(y_true, y_prob))
    except Exception:
        auroc = None

    try:
        ap = float(average_precision_score(y_true, y_prob))
    except Exception:
        ap = None

    return {
        "roc_auc": auroc,
        "average_precision": ap,
        "prevalence": prevalence,
    }

