"""Local Wisconsin monitoring context to accompany OpenAI bloom labeling."""

from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ESP_DEPLOYMENT_CSV = REPO_ROOT / "data" / "esp_deployment_data_CSV.csv"

STATION_CONTEXT = (
    "USGS-040851385 — Fox River at Oil Tank Depot at Green Bay, WI "
    "(Green Bay / lower Fox River harmful algal bloom monitoring area)."
)

DNR_GUIDANCE = (
    "Cross-check Wisconsin DNR (WDNR) public harmful algal bloom reporting, "
    "beach advisories, and Green Bay / Fox River cyanobacteria updates when "
    "the target date falls in the warm season (roughly May–October). "
    "Prefer WDNR-confirmed bloom periods and advisory language over isolated "
    "pigment spikes alone. Do not treat fluorescence proxies as toxin confirmation."
)


def _parse_esp_date(raw: str) -> date:
    return datetime.strptime(raw.strip(), "%m/%d/%Y").date()


def load_esp_samples(path: Path = ESP_DEPLOYMENT_CSV) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    rows: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if not row.get("Date"):
                continue
            rows.append(
                {
                    "station": row.get("Station", "").strip(),
                    "date": row["Date"].strip(),
                    "depth": row.get("depth", "").strip(),
                    "microcystin_ug_l": row.get("MC ug L-1", "").strip(),
                }
            )
    return rows


def esp_context_for_date(
    target: date,
    samples: list[dict[str, str]],
    *,
    window_days: int = 14,
) -> str:
    """Summarize nearby ESP microcystin measurements (Green Bay deployments)."""
    if not samples:
        return "No local ESP microcystin deployment CSV entries loaded."

    start = target - timedelta(days=window_days)
    end = target + timedelta(days=window_days)
    nearby: list[str] = []
    for sample in samples:
        try:
            sample_date = _parse_esp_date(sample["date"])
        except ValueError:
            continue
        if start <= sample_date <= end:
            nearby.append(
                f"{sample_date.isoformat()} {sample['station']} ({sample['depth']}): "
                f"MC={sample['microcystin_ug_l']} ug/L"
            )
    if not nearby:
        return (
            f"No ESP microcystin samples within ±{window_days} days of {target.isoformat()}."
        )
    return "Nearby ESP microcystin samples (WDNR-related field monitoring):\n" + "\n".join(
        nearby
    )


def build_decision_context(
    *,
    target_date: str,
    feature_row: dict[str, object],
    esp_samples: list[dict[str, str]],
) -> str:
    """Text bundle passed to the Decisions API as shared input."""
    day = date.fromisoformat(target_date)
    esp_block = esp_context_for_date(day, esp_samples)
    feature_lines = "\n".join(
        f"  {key}: {feature_row[key]}" for key in sorted(feature_row) if key not in {"date", "station_id"}
    )
    return (
        f"{STATION_CONTEXT}\n\n"
        f"{DNR_GUIDANCE}\n\n"
        f"Target date: {target_date}\n"
        f"Station: {feature_row.get('station_id')}\n\n"
        f"Daily USGS sensor aggregates (missing values imputed with column means):\n"
        f"{feature_lines}\n\n"
        f"{esp_block}\n"
    )
