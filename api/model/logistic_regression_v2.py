"""Train a mean-only bloom classifier and predict from Tiger Data measurements.

Run from api: uv run python model/logistic_regression_v2.py
Training uses daily means. Live inference uses instantaneous measurements as
requested, so validation on daily means does not validate live performance.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import pickle
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np
import sklearn
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

DEFAULT_DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "labeled_openai.csv"
DEFAULT_MODEL_PATH = Path(__file__).with_name("artifacts") / "logistic_regression_v2.pkl"
FEATURE_PARAMETERS = {
    "chlorophyll_fluorescence_mean": "32316",
    "discharge_mean": "00060",
    "dissolved_oxygen_mean": "00300",
    "phycocyanin_fluorescence_mean": "32319",
    "specific_conductance_mean": "00095",
    "turbidity_mean": "63680",
    "water_temperature_mean": "00010",
}
FEATURE_COLUMNS = tuple(FEATURE_PARAMETERS)


def load_data(path: str | Path = DEFAULT_DATA_PATH):
    features, labels = [], []
    with Path(path).open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        missing = set((*FEATURE_COLUMNS, "algal_bloom")) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing columns: {sorted(missing)}")
        for line, row in enumerate(reader, start=2):
            if row["algal_bloom"] not in {"0", "1"}:
                raise ValueError(f"Row {line}: algal_bloom must be 0 or 1")
            try:
                values = [float(row[name]) for name in FEATURE_COLUMNS]
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Row {line}: mean features must be numeric and present") from exc
            if not np.isfinite(values).all():
                raise ValueError(f"Row {line}: mean features must be finite")
            features.append(values)
            labels.append(int(row["algal_bloom"]))
    if set(labels) != {0, 1}:
        raise ValueError("Training requires both classes")
    return np.asarray(features), np.asarray(labels)


def build_model():
    return Pipeline([
        ("scaler", StandardScaler()),
        ("classifier", LogisticRegression(class_weight="balanced", max_iter=2000, random_state=42)),
    ])


def train_model(path: str | Path = DEFAULT_DATA_PATH):
    x, y = load_data(path)
    return build_model().fit(x, y)


def train_and_save(data_path=DEFAULT_DATA_PATH, model_path=DEFAULT_MODEL_PATH):
    x, y = load_data(data_path)
    folds = min(5, int(np.bincount(y).min()))
    if folds < 2:
        raise ValueError("At least two examples of each class are required for validation")
    cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=42)
    probabilities = cross_val_predict(build_model(), x, y, cv=cv, method="predict_proba")[:, 1]
    report = {
        "model_version": "logistic_regression_v2",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "training_file": Path(data_path).name,
        "training_sha256": hashlib.sha256(Path(data_path).read_bytes()).hexdigest(),
        "sklearn_version": sklearn.__version__,
        "feature_columns": list(FEATURE_COLUMNS),
        "feature_parameters": FEATURE_PARAMETERS,
        "training_rows": len(y),
        "class_counts": {str(i): int((y == i).sum()) for i in (0, 1)},
        "validation": f"{folds}-fold stratified shuffled cross-validation; not a forecasting evaluation",
        "classification_report": classification_report(y, probabilities >= 0.5, output_dict=True, zero_division=0),
        "confusion_matrix": confusion_matrix(y, probabilities >= 0.5).tolist(),
        "roc_auc": float(roc_auc_score(y, probabilities)),
        "limitations": [
            "Few positive labels; validation estimates are uncertain and do not establish confirmed bloom detection.",
            "Live inputs are instantaneous measurements; training inputs are daily means.",
            "Class-weighted probabilities are model scores, not calibrated bloom risks.",
        ],
    }
    artifact = {"model": build_model().fit(x, y), "metadata": report}
    destination = Path(model_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    with temporary.open("wb") as target:
        pickle.dump(artifact, target)
    temporary.replace(destination)
    destination.with_suffix(".json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


@lru_cache(maxsize=1)
def _load_model(path: str, modified_ns: int):
    # Only load our locally generated artifact, never a client-supplied pickle.
    with Path(path).open("rb") as source:
        artifact = pickle.load(source)
    if artifact["metadata"]["feature_columns"] != list(FEATURE_COLUMNS):
        raise ValueError("Saved model features do not match v2")
    return artifact


def predict_readings(readings, model_path=DEFAULT_MODEL_PATH):
    """Use resolved latest/last-known readings; never impute absent live values."""
    by_parameter = {reading["parameter_code"]: reading for reading in readings}
    inputs, missing = [], []
    for feature, parameter in FEATURE_PARAMETERS.items():
        reading = by_parameter.get(parameter)
        value = reading.get("value") if reading else None
        if value is None or not np.isfinite(float(value)):
            missing.append(feature)
        else:
            inputs.append({"feature": feature, **reading})
    if missing:
        return {"status": "unavailable", "missing_features": missing,
                "reason": "No measured value exists for one or more required features", "inputs": inputs}
    path = Path(model_path).resolve()
    artifact = _load_model(str(path), path.stat().st_mtime_ns)
    x = np.asarray([[reading["value"] for reading in inputs]], dtype=float)
    probability = float(artifact["model"].predict_proba(x)[0, 1])
    return {
        "status": "available",
        "model_version": "logistic_regression_v2",
        "trained_at": artifact["metadata"]["trained_at"],
        "algal_bloom": int(probability >= 0.5),
        "probability": probability,
        "threshold": 0.5,
        "inputs": inputs,
        "input_mode": "latest_instantaneous_with_last_measured_fallback",
        "limitations": artifact["metadata"]["limitations"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_MODEL_PATH)
    args = parser.parse_args()
    print(json.dumps(train_and_save(args.data, args.output), indent=2))
