from __future__ import annotations

import numpy as np
from dataclasses import dataclass

from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from shiftguard.datasets.bank import BANK_FEATURES


NUMERIC_FEATURES = ("age", "pdays", "previous")
CATEGORICAL_FEATURES = tuple(feature for feature in BANK_FEATURES if feature not in NUMERIC_FEATURES)
NUMERIC_INDICES = tuple(BANK_FEATURES.index(feature) for feature in NUMERIC_FEATURES)
CATEGORICAL_INDICES = tuple(BANK_FEATURES.index(feature) for feature in CATEGORICAL_FEATURES)
EXPLICIT_MISSING_CATEGORY = "__SHIFTGUARD_MISSING__"


def rows_to_features(rows: list[dict[str, str | int]]) -> np.ndarray:
    def value(row: dict[str, str | int], feature: str) -> float | str:
        raw = row.get(feature)
        if feature in NUMERIC_FEATURES:
            return np.nan if raw in (None, "") else float(raw)
        return EXPLICIT_MISSING_CATEGORY if raw in (None, "") else str(raw)

    return np.asarray([[value(row, feature) for feature in BANK_FEATURES] for row in rows], dtype=object)


def feature_rows(rows: list[dict[str, str | int]]) -> list[dict[str, str | int]]:
    return [{feature: row[feature] for feature in BANK_FEATURES} for row in rows]


@dataclass
class TrainOnlyPreprocessor:
    transformer: ColumnTransformer

    def transform(self, rows: list[dict[str, str | int]]):
        return self.transformer.transform(rows_to_features(rows))


def fit_train_preprocessor(train_rows: list[dict[str, str | int]]) -> TrainOnlyPreprocessor:
    preprocessor = ColumnTransformer([
        ("numeric", Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]), list(NUMERIC_INDICES)),
        ("categorical", OneHotEncoder(handle_unknown="ignore"), list(CATEGORICAL_INDICES)),
    ])
    preprocessor.fit(rows_to_features(train_rows))
    return TrainOnlyPreprocessor(preprocessor)


def fit_tree_preprocessor(train_rows: list[dict[str, str | int]]) -> TrainOnlyPreprocessor:
    """Preprocessor for tree models: median imputation on numerics (no scaler), OHE on categoricals."""
    preprocessor = ColumnTransformer([
        ("numeric", SimpleImputer(strategy="median"), list(NUMERIC_INDICES)),
        ("categorical", OneHotEncoder(handle_unknown="ignore"), list(CATEGORICAL_INDICES)),
    ])
    preprocessor.fit(rows_to_features(train_rows))
    return TrainOnlyPreprocessor(preprocessor)


def preprocessing_config(model_family: str = "linear") -> dict[str, object]:
    if model_family == "tree":
        return {
            "model_family": "tree",
            "numeric_features": list(NUMERIC_FEATURES),
            "numeric": {"imputer": "median", "scaler": None},
            "categorical_features": list(CATEGORICAL_FEATURES),
            "categorical": {"missing_value": EXPLICIT_MISSING_CATEGORY, "encoder": "one_hot", "handle_unknown": "ignore"},
        }
    return {
        "model_family": "linear",
        "numeric_features": list(NUMERIC_FEATURES),
        "numeric": {"imputer": "median", "scaler": "standard"},
        "categorical_features": list(CATEGORICAL_FEATURES),
        "categorical": {"missing_value": EXPLICIT_MISSING_CATEGORY, "encoder": "one_hot", "handle_unknown": "ignore"},
    }
