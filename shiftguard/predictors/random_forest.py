from __future__ import annotations

from sklearn.ensemble import RandomForestClassifier

from shiftguard.preprocessing.tabular import TrainOnlyPreprocessor


def fit_initial_random_forest(features, labels: list[int], seed: int) -> RandomForestClassifier:
    """Fit frozen Random Forest classifier with n_jobs=1 for deterministic cross-platform execution."""
    model = RandomForestClassifier(
        n_estimators=100,
        max_depth=None,
        min_samples_split=2,
        min_samples_leaf=1,
        random_state=seed,
        n_jobs=1,
    )
    model.fit(features, labels)
    return model


def random_forest_identity(model: RandomForestClassifier) -> dict[str, object]:
    return {
        "model_type": "sklearn.ensemble.RandomForestClassifier",
        "resolved_hyperparameters": model.get_params(deep=False),
    }


def fitted_rf_state(preprocessor: TrainOnlyPreprocessor, predictor: RandomForestClassifier) -> dict[str, object]:
    numeric = preprocessor.transformer.named_transformers_["numeric"]
    categorical = preprocessor.transformer.named_transformers_["categorical"]
    return {
        "numeric_medians": numeric.statistics_.tolist(),
        "categories": [values.tolist() for values in categorical.categories_],
        "n_estimators": len(predictor.estimators_),
        "classes": predictor.classes_.tolist(),
        "n_features_in": int(predictor.n_features_in_),
    }
