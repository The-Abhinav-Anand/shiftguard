from __future__ import annotations

from sklearn.linear_model import LogisticRegression


def fit_initial_logistic_regression(features, labels: list[int], seed: int) -> LogisticRegression:
    model = LogisticRegression(random_state=seed, max_iter=1000)
    model.fit(features, labels)
    return model


def predictor_identity(model: LogisticRegression) -> dict[str, object]:
    return {
        "model_type": "sklearn.linear_model.LogisticRegression",
        "resolved_hyperparameters": model.get_params(deep=False),
    }
