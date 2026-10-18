"""
USGS / Foxwatch parameter labels shared with ``data/attributes/usgs_parameter_manifest.csv``.

BFI scoring uses ``condition_predictor`` attributes from the manifest. Bloom fluorescence
proxies (``bloom_indicator`` role) are reference thresholds only — they are not BFI points.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

from ..config import USGS_MANIFEST_PATH

DEFAULT_MANIFEST_PATH = USGS_MANIFEST_PATH

# USGS operational limits from time-series metadata (Fox River mouth, USGS-040851385).
# Used for cross-check context only; BFI rules use separate published driver thresholds.
USGS_REFERENCE_THRESHOLDS: dict[str, dict[str, float]] = {
    "32319": {"high_ug_l": 125.0},  # phycocyanin_fluorescence
    "32316": {"high_ug_l": 100.0},  # chlorophyll_fluorescence
    "00010": {"very_high_deg_c": 35.0},  # water_temperature
}

MM_PER_INCH = 25.4


@dataclass(frozen=True)
class ParameterSpec:
    """One row from the USGS parameter manifest."""

    parameter_code: str
    attribute: str
    description: str
    unit: str
    role: str
    priority: str
    notes: str


@dataclass(frozen=True)
class BfiFactorSpec:
    """Maps a BFI scorer to Foxwatch / USGS labels."""

    bfi_key: str
    factor_label: str
    attribute: str
    parameter_code: Optional[str]
    unit: str
    role: str
    source: str


# BFI keys → manifest-aligned labels (see usgs_parameter_manifest.csv).
BFI_FACTOR_SPECS: dict[str, BfiFactorSpec] = {
    "water_temperature_c": BfiFactorSpec(
        bfi_key="water_temperature_c",
        factor_label="Water temperature",
        attribute="water_temperature",
        parameter_code="00010",
        unit="deg C",
        role="condition_predictor",
        source="USGS",
    ),
    "phosphorus_ug_l": BfiFactorSpec(
        bfi_key="phosphorus_ug_l",
        factor_label="Orthophosphate, water, filtered",
        attribute="orthophosphate_dissolved",
        parameter_code="00671",
        unit="ug/L as P (converted from mg/L as P when needed)",
        role="condition_predictor",
        source="USGS",
    ),
    "nitrogen_mg_l": BfiFactorSpec(
        bfi_key="nitrogen_mg_l",
        factor_label="Nitrate plus nitrite, water, filtered",
        attribute="nitrate_nitrite_dissolved",
        parameter_code="00631",
        unit="mg/L as N",
        role="condition_predictor",
        source="USGS",
    ),
    "streamflow_cfs": BfiFactorSpec(
        bfi_key="streamflow_cfs",
        factor_label="Discharge",
        attribute="discharge",
        parameter_code="00060",
        unit="ft3/s",
        role="condition_predictor",
        source="USGS",
    ),
    "rainfall_7day_in": BfiFactorSpec(
        bfi_key="rainfall_7day_in",
        factor_label="Precipitation (7-day total)",
        attribute="precipitation",
        parameter_code=None,
        unit="in",
        role="condition_predictor",
        source="NOAA",
    ),
    "solar_radiation_level": BfiFactorSpec(
        bfi_key="solar_radiation_level",
        factor_label="Solar radiation",
        attribute="solar_radiation",
        parameter_code=None,
        unit="category",
        role="condition_predictor",
        source="external",
    ),
}


def load_parameter_manifest(path: Path | None = None) -> dict[str, ParameterSpec]:
    """
    Load ``usgs_parameter_manifest.csv`` keyed by ``attribute`` name.

    Raises:
        FileNotFoundError: If the manifest path does not exist.
    """
    manifest_path = path or DEFAULT_MANIFEST_PATH
    specs: dict[str, ParameterSpec] = {}
    with manifest_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            spec = ParameterSpec(
                parameter_code=row["parameter_code"],
                attribute=row["attribute"],
                description=row["description"],
                unit=row["unit"],
                role=row["role"],
                priority=row["priority"],
                notes=row["notes"],
            )
            specs[spec.attribute] = spec
    return specs


def factor_metadata(bfi_key: str) -> dict[str, Any]:
    """JSON-friendly manifest labels for one BFI input."""
    spec = BFI_FACTOR_SPECS[bfi_key]
    return {
        "factor": spec.factor_label,
        "attribute": spec.attribute,
        "parameter_code": spec.parameter_code,
        "unit": spec.unit,
        "role": spec.role,
        "source": spec.source,
    }


def mg_p_as_p_to_ug_l(value_mg_l_as_p: float) -> float:
    """Convert USGS phosphorus (mg/L as P) to µg/L for BFI phosphorus rules."""
    return value_mg_l_as_p * 1000.0


def mm_to_inches(value_mm: float) -> float:
    """Convert NOAA daily precipitation (mm) to inches."""
    return value_mm / MM_PER_INCH


def resolve_phosphorus_ug_l(
    *,
    phosphorus_ug_l: Optional[float] = None,
    orthophosphate_mg_l_as_p: Optional[float] = None,
    total_phosphorus_mg_l_as_p: Optional[float] = None,
) -> Optional[float]:
    """
    Resolve phosphorus for BFI scoring.

    Prefers explicit ``phosphorus_ug_l``; otherwise converts manifest orthophosphate
    (00671) or total phosphorus (00665) from mg/L as P.
    """
    if phosphorus_ug_l is not None:
        return float(phosphorus_ug_l)
    if orthophosphate_mg_l_as_p is not None:
        return mg_p_as_p_to_ug_l(float(orthophosphate_mg_l_as_p))
    if total_phosphorus_mg_l_as_p is not None:
        return mg_p_as_p_to_ug_l(float(total_phosphorus_mg_l_as_p))
    return None


def resolve_nitrogen_mg_l(
    *,
    nitrogen_mg_l: Optional[float] = None,
    nitrate_nitrite_mg_l_as_n: Optional[float] = None,
    ammonia_mg_l_as_n: Optional[float] = None,
) -> Optional[float]:
    """
    Resolve inorganic nitrogen for BFI scoring (mg/L as N).

    Uses nitrate+nitrite (00631) when present; optionally adds ammonia (00608).
    """
    if nitrogen_mg_l is not None:
        return float(nitrogen_mg_l)
    total = 0.0
    found = False
    if nitrate_nitrite_mg_l_as_n is not None:
        total += float(nitrate_nitrite_mg_l_as_n)
        found = True
    if ammonia_mg_l_as_n is not None:
        total += float(ammonia_mg_l_as_n)
        found = True
    return total if found else None


def sum_precipitation_7day_in(
    observations: list[Mapping[str, Any]],
    *,
    end_date: str,
    metric: str = "precipitation",
) -> Optional[float]:
    """
    Sum daily precipitation ending on ``end_date`` (inclusive) over 7 days.

    Accepts values in mm (Foxwatch demo / NOAA) or inches (``unit`` contains ``in``).
    """
    by_date: dict[str, float] = {}
    for obs in observations:
        if obs.get("metric") != metric:
            continue
        date = obs.get("observation_date")
        value = obs.get("value")
        if date is None or value is None:
            continue
        unit = str(obs.get("unit", "mm")).lower()
        amount_in = float(value) / MM_PER_INCH if "mm" in unit else float(value)
        by_date[str(date)] = by_date.get(str(date), 0.0) + amount_in

    if not by_date:
        return None

    from datetime import date, timedelta

    end = date.fromisoformat(end_date)
    total = 0.0
    days = 0
    for offset in range(7):
        day = (end - timedelta(days=offset)).isoformat()
        if day in by_date:
            total += by_date[day]
            days += 1
    return total if days else None


def load_usgs_daily_values(
    path: Path,
    *,
    parameter_code: str,
    statistic_id: str = "00003",
) -> dict[str, float]:
    """
    Load daily USGS export values keyed by ISO date (``YYYY-MM-DD``).

    Default statistic ``00003`` is daily mean where present in Foxwatch exports.
    """
    values: dict[str, float] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["parameter_code"] != parameter_code:
                continue
            if row["statistic_id"] != statistic_id:
                continue
            values[row["time"]] = float(row["value"])
    return values


def median_discharge_for_month(
    discharge_by_date: Mapping[str, float],
    *,
    month: int,
) -> Optional[float]:
    """Seasonal median discharge (cfs) for calendar month across available years."""
    month_values = [
        value
        for date_str, value in discharge_by_date.items()
        if int(date_str[5:7]) == month
    ]
    if not month_values:
        return None
    month_values.sort()
    mid = len(month_values) // 2
    if len(month_values) % 2:
        return month_values[mid]
    return (month_values[mid - 1] + month_values[mid]) / 2.0


def assert_bfi_labels_match_manifest(manifest: dict[str, ParameterSpec] | None = None) -> None:
    """
    Verify BFI factor labels stay aligned with ``usgs_parameter_manifest.csv``.

    Raises:
        AssertionError: When a mapped attribute is missing or description drifts.
    """
    manifest = manifest or load_parameter_manifest()
    for spec in BFI_FACTOR_SPECS.values():
        if spec.parameter_code is None:
            continue
        row = manifest.get(spec.attribute)
        assert row is not None, f"Missing manifest attribute {spec.attribute!r}"
        assert row.parameter_code == spec.parameter_code
        assert row.role == spec.role
        assert spec.factor_label == row.description, (
            f"Label drift for {spec.attribute}: "
            f"BFI={spec.factor_label!r} manifest={row.description!r}"
        )
