"""
Build daily USGS feature rows from data/attributes/*-daily.csv (in memory),
label algal_bloom via OpenAI Decisions API, and write data/labeled_openai.csv.

Requires: openai package, OPENAI_API_KEY in environment or repo-root .env
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from dnr_context import build_decision_context, load_esp_samples
from usgs_daily_features import (
    DEFAULT_DAILY_CSV,
    FEATURE_COLUMNS,
    build_daily_features,
    column_means,
    impute_missing_with_means,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "data" / "labeled_openai.csv"
DECISIONS_MODEL = "gpt-6-luna"

BLOOM_QUESTION = {
    "type": "choice",
    "name": "algal_bloom",
    "instructions": (
        "You are labeling training data for traditional ML (binary ground truth). "
        "Choose 1 only if Wisconsin DNR public HAB/beach reporting or strong field "
        "evidence supports a meaningful algal or cyanobacteria bloom on this date at "
        "the Fox River / Green Bay site, AND daily sensor features (especially "
        "chlorophyll and phycocyanin fluorescence, turbidity, temperature, dissolved "
        "oxygen) indicate a high likelihood of bloom conditions. "
        "Choose 0 if conditions appear normal, ambiguous, proxy-only without bloom "
        "support, or inconsistent with WDNR reporting. "
        "Be conservative: avoid labeling 1 from pigment spikes alone."
    ),
    "choices": [
        {
            "value": "0",
            "description": "No bloom — normal or insufficient evidence for bloom conditions.",
        },
        {
            "value": "1",
            "description": "Bloom — WDNR context and sensors support likely bloom conditions.",
        },
    ],
}


def load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def require_openai_client():
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise SystemExit(
            "Install the openai package (e.g. uv add openai) before running this script."
        ) from exc
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is not set (use repo-root .env or environment).")
    return OpenAI(api_key=api_key)


def classify_bloom(client: Any, context: str) -> str:
    decision = client.decisions.create(
        model=DECISIONS_MODEL,
        input=context,
        questions=[BLOOM_QUESTION],
    )
    if not decision.answers:
        raise RuntimeError("Decisions API returned no answers")
    answer = decision.answers[0]
    if answer.type == "refusal":
        raise RuntimeError(f"Model refused bloom question: {answer.name}")
    if answer.type != "choice":
        raise RuntimeError(f"Unexpected answer type: {answer.type}")
    choice = str(answer.choice)
    if choice not in {"0", "1"}:
        raise RuntimeError(f"Unexpected choice value: {choice!r}")
    return choice


def write_labeled_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = ["date", "station_id", *FEATURE_COLUMNS, "algal_bloom"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] for key in fieldnames})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--daily-csv",
        type=Path,
        default=DEFAULT_DAILY_CSV,
        help="USGS daily attribute export (long format).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output CSV path (features + algal_bloom).",
    )
    parser.add_argument(
        "--station-id",
        default="USGS-040851385",
        help="Monitoring location id filter.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Label at most N rows (for testing).",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.0,
        help="Pause between Decisions API calls.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_dotenv(REPO_ROOT / ".env")

    if not args.daily_csv.is_file():
        print(f"Daily CSV not found: {args.daily_csv}", file=sys.stderr)
        return 1

    raw_rows = build_daily_features(args.daily_csv, station_id=args.station_id)
    means = column_means(raw_rows)
    feature_rows = impute_missing_with_means(raw_rows, means)

    if args.limit is not None:
        feature_rows = feature_rows[: args.limit]

    client = require_openai_client()
    esp_samples = load_esp_samples()

    labeled: list[dict[str, Any]] = []
    total = len(feature_rows)
    for index, row in enumerate(feature_rows, start=1):
        context = build_decision_context(
            target_date=row["date"],
            feature_row=row,
            esp_samples=esp_samples,
        )
        bloom = classify_bloom(client, context)
        labeled.append({**row, "algal_bloom": bloom})
        print(f"[{index}/{total}] {row['date']} -> algal_bloom={bloom}")
        if args.sleep_seconds > 0 and index < total:
            time.sleep(args.sleep_seconds)

    write_labeled_csv(args.output, labeled)
    print(f"Wrote {len(labeled)} rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
