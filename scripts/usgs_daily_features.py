"""Pivot USGS daily attribute exports into labeled.csv-style feature rows."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DAILY_CSV = (
    REPO_ROOT / "data" / "attributes" / "2026-10-17T22-56-42.689Z-daily.csv"
)

FEATURE_COLUMNS: tuple[str, ...] = (
    "chlorophyll_fluorescence_max",
    "chlorophyll_fluorescence_mean",
    "chlorophyll_fluorescence_min",
    "discharge_mean",
    "dissolved_oxygen_max",
    "dissolved_oxygen_mean",
    "dissolved_oxygen_min",
    "ph_max",
    "ph_median",
    "ph_min",
    "phycocyanin_fluorescence_max",
    "phycocyanin_fluorescence_mean",
    "phycocyanin_fluorescence_min",
    "specific_conductance_max",
    "specific_conductance_mean",
    "specific_conductance_min",
    "turbidity_max",
    "turbidity_mean",
    "turbidity_min",
    "water_temperature_max",
    "water_temperature_mean",
    "water_temperature_min",
)

# USGS parameter_code + statistic_id → feature column (matches data/labeled.csv).
_PARAMETER_STATISTIC_TO_COLUMN: dict[tuple[str, str], str] = {
    ("32316", "00001"): "chlorophyll_fluorescence_max",
    ("32316", "00003"): "chlorophyll_fluorescence_mean",
    ("32316", "00002"): "chlorophyll_fluorescence_min",
    ("00060", "00003"): "discharge_mean",
    ("00300", "00001"): "dissolved_oxygen_max",
    ("00300", "00003"): "dissolved_oxygen_mean",
    ("00300", "00002"): "dissolved_oxygen_min",
    ("00400", "00001"): "ph_max",
    ("00400", "00008"): "ph_median",
    ("00400", "00002"): "ph_min",
    ("32319", "00001"): "phycocyanin_fluorescence_max",
    ("32319", "00003"): "phycocyanin_fluorescence_mean",
    ("32319", "00002"): "phycocyanin_fluorescence_min",
    ("00095", "00001"): "specific_conductance_max",
    ("00095", "00003"): "specific_conductance_mean",
    ("00095", "00002"): "specific_conductance_min",
    ("63680", "00001"): "turbidity_max",
    ("63680", "00003"): "turbidity_mean",
    ("63680", "00002"): "turbidity_min",
    ("00010", "00001"): "water_temperature_max",
    ("00010", "00003"): "water_temperature_mean",
    ("00010", "00002"): "water_temperature_min",
}


@dataclass(frozen=True)
class DailyFeatureRow:
    date: str
    station_id: str
    features: dict[str, Optional[float]]


def _parse_value(raw: str) -> Optional[float]:
    text = raw.strip()
    if not text:
        return None
    return float(text)


def build_daily_features(
    daily_csv: Path,
    *,
    station_id: Optional[str] = None,
) -> list[DailyFeatureRow]:
    """
    Load long-format USGS daily values and pivot to one row per calendar day.

    Rows are ordered by date. Missing feature cells are ``None`` until imputation.
    """
    by_date: dict[str, dict[str, Optional[float]]] = {}
    stations: dict[str, str] = {}

    with daily_csv.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            column = _PARAMETER_STATISTIC_TO_COLUMN.get(
                (row["parameter_code"], row["statistic_id"])
            )
            if column is None:
                continue

            date = row["time"]
            loc = row["monitoring_location_id"]
            if station_id is not None and loc != station_id:
                continue

            stations[date] = loc
            value = _parse_value(row["value"])
            day = by_date.setdefault(date, {})
            day[column] = value

    if station_id is not None and not by_date:
        raise ValueError(f"No rows found for station {station_id!r} in {daily_csv}")

    resolved_station = station_id
    if resolved_station is None:
        unique = {s for s in stations.values()}
        if len(unique) != 1:
            raise ValueError(
                "Daily export contains multiple monitoring_location_id values; "
                f"pass station_id explicitly. Found: {sorted(unique)}"
            )
        resolved_station = next(iter(unique))

    rows: list[DailyFeatureRow] = []
    for date in sorted(by_date):
        features = {col: by_date[date].get(col) for col in FEATURE_COLUMNS}
        rows.append(
            DailyFeatureRow(
                date=date,
                station_id=stations.get(date, resolved_station),
                features=features,
            )
        )
    return rows


def column_means(rows: Sequence[DailyFeatureRow]) -> dict[str, float]:
    """Mean of each feature column, ignoring missing values."""
    totals: dict[str, float] = {col: 0.0 for col in FEATURE_COLUMNS}
    counts: dict[str, int] = {col: 0 for col in FEATURE_COLUMNS}
    for row in rows:
        for col in FEATURE_COLUMNS:
            value = row.features.get(col)
            if value is None:
                continue
            totals[col] += value
            counts[col] += 1
    means: dict[str, float] = {}
    for col in FEATURE_COLUMNS:
        if counts[col] == 0:
            raise ValueError(f"No observed values for feature column {col!r}")
        means[col] = totals[col] / counts[col]
    return means


def impute_missing_with_means(
    rows: list[DailyFeatureRow],
    means: Mapping[str, float],
) -> list[dict[str, Any]]:
    """Return flat dict rows with all feature columns filled (in memory only)."""
    filled: list[dict[str, Any]] = []
    for row in rows:
        record: dict[str, Any] = {
            "date": row.date,
            "station_id": row.station_id,
        }
        for col in FEATURE_COLUMNS:
            value = row.features.get(col)
            record[col] = value if value is not None else means[col]
        filled.append(record)
    return filled
