"""Predict the CSV's binary pigment-proxy labels from water measurements.

These labels are unvalidated proxies, not confirmed algal blooms. Run this
module to evaluate a reproducible stratified holdout; use train_model() to fit
all rows for inference. Prediction arrays must follow FEATURE_COLUMNS order.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

DEFAULT_DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "labeled.csv"
TARGET_COLUMN = "algal_bloom"
# Exclude identifiers, label metadata, pigment_proxy_score and label_threshold.
FEATURE_COLUMNS = (
    "chlorophyll_fluorescence_mean",
    "discharge_mean",
    "dissolved_oxygen_mean",
    "ph_median",
    "phycocyanin_fluorescence_mean",
    "specific_conductance_mean",
    "turbidity_mean",
    "water_temperature_mean",
)


def load_data(path: str | Path = DEFAULT_DATA_PATH) -> tuple[np.ndarray, np.ndarray]:
    """Load measurements in a fixed order, representing blank values as NaN."""
    features, labels = [], []
    with Path(path).open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        missing = set((*FEATURE_COLUMNS, TARGET_COLUMN)) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")
        for line, row in enumerate(reader, start=2):
            label = (row[TARGET_COLUMN] or "").strip()
            if label not in {"0", "1"}:
                raise ValueError(f"Row {line}: algal_bloom must be 0 or 1")
            try:
                values = [
                    float(row[column]) if (row[column] or "").strip() else np.nan
                    for column in FEATURE_COLUMNS
                ]
            except ValueError as exc:
                raise ValueError(f"Row {line}: measurements must be numeric") from exc
            if np.isinf(values).any():
                raise ValueError(f"Row {line}: measurements cannot be infinite")
            features.append(values)
            labels.append(int(label))
    if set(labels) != {0, 1}:
        raise ValueError("Training data must contain both binary classes (0 and 1)")
    return np.asarray(features, dtype=float), np.asarray(labels, dtype=int)


def build_model() -> Pipeline:
    """Keep preprocessing inside the pipeline so holdout data never fits it."""
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
        ("scaler", StandardScaler()),
        ("classifier", LogisticRegression(max_iter=2000, random_state=42)),
    ])


def train_model(path: str | Path = DEFAULT_DATA_PATH) -> Pipeline:
    """Fit all labeled rows; supports predict(X) and predict_proba(X)[:, 1]."""
    features, labels = load_data(path)
    return build_model().fit(features, labels)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_PATH)
    args = parser.parse_args()
    features, labels = load_data(args.data)
    x_train, x_test, y_train, y_test = train_test_split(
        features, labels, test_size=0.2, stratify=labels, random_state=42,
    )
    model = build_model().fit(x_train, y_train)
    predictions = model.predict(x_test)
    print(f"Training rows: {len(y_train)}; holdout rows: {len(y_test)}")
    print("Target: unvalidated pigment-proxy label, not confirmed blooms.")
    print("Random holdout measures label reproduction, not future forecasting.")
    print(classification_report(y_test, predictions, digits=3, zero_division=0))
    print("Confusion matrix (rows=actual, columns=predicted; classes 0, 1):")
    print(confusion_matrix(y_test, predictions, labels=[0, 1]))
    print(f"ROC AUC: {roc_auc_score(y_test, model.predict_proba(x_test)[:, 1]):.3f}")


if __name__ == "__main__":
    main()
