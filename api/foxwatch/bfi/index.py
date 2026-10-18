"""
Bloom Favorability Index (BFI) — rule-based environmental favorability scoring.

This module evaluates whether observed conditions align with published drivers of
algal bloom formation (temperature, nutrients, hydrology, rainfall, sunlight).
It does not predict blooms via machine learning; every point is traceable to
explicit thresholds.

The public API is ``calculate_bloom_favorability``. The default implementation
delegates to ``RuleBasedScoringEngine``, which can be replaced without changing
call signatures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping, Optional, Protocol, Sequence

from foxwatch.bfi.labels import (
    BFI_FACTOR_SPECS,
    factor_metadata,
    resolve_nitrogen_mg_l,
    resolve_phosphorus_ug_l,
    sum_precipitation_7day_in,
)

# ---------------------------------------------------------------------------
# Configurable thresholds
# ---------------------------------------------------------------------------

# Water temperature (°C)
TEMP_COLD_MAX_C = 20.0
TEMP_WARM_MAX_C = 25.0

# Phosphorus (µg/L)
PHOSPHORUS_LOW_MAX_UG_L = 20.0
PHOSPHORUS_MODERATE_MAX_UG_L = 50.0

# Nitrogen (mg/L)
NITROGEN_LOW_MAX_MG_L = 0.5
NITROGEN_MODERATE_MAX_MG_L = 1.0

# Streamflow relative to seasonal median
STREAMFLOW_LOW_FRACTION_OF_MEDIAN = 0.90
STREAMFLOW_NEAR_MEDIAN_BAND = 0.10

# Rainfall — previous 7 days (inches)
RAINFALL_DRY_MAX_IN = 0.5
RAINFALL_MODERATE_MAX_IN = 2.0

# Classification breakpoints (raw score when all factors present; max = 12)
CLASSIFICATION_LOW_MAX_SCORE = 3
CLASSIFICATION_MODERATE_MAX_SCORE = 7
CLASSIFICATION_HIGH_MAX_SCORE = 10
# Scores above CLASSIFICATION_HIGH_MAX_SCORE through max possible → VERY HIGH

MAX_POINTS_PER_FACTOR = 2
FACTOR_COUNT = 6

SOLAR_RADIATION_LEVELS = frozenset({"low", "moderate", "high"})


class FavorabilityClassification(str, Enum):
    """Bloom favorability tier derived from score relative to maximum possible."""

    LOW = "LOW FAVORABILITY"
    MODERATE = "MODERATE FAVORABILITY"
    HIGH = "HIGH FAVORABILITY"
    VERY_HIGH = "VERY HIGH FAVORABILITY"


@dataclass(frozen=True)
class FactorScore:
    """Score contribution from a single environmental driver."""

    factor: str
    value: Any
    points: int
    status: str
    reason: Optional[str] = None


@dataclass
class BloomFavorabilityResult:
    """Complete BFI output (JSON-serializable via ``to_dict``)."""

    score: int
    max_possible_score: int
    favorability_percent: float
    classification: str
    factors: list[dict[str, Any]] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return the standard JSON-shaped response payload."""
        return {
            "score": self.score,
            "max_possible_score": self.max_possible_score,
            "favorability_percent": self.favorability_percent,
            "classification": self.classification,
            "factors": self.factors,
            "reasons": self.reasons,
        }


def _is_missing(value: Any) -> bool:
    """Return True if a measurement should be treated as unavailable."""
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _status_for_points(points: int) -> str:
    if points >= 2:
        return "Favorable"
    if points == 1:
        return "Moderately favorable"
    return "Not favorable"


# ---------------------------------------------------------------------------
# Per-factor scorers (each returns points and an optional explainability reason)
# ---------------------------------------------------------------------------


def score_water_temperature(water_temperature_c: float) -> tuple[int, Optional[str]]:
    """
    Score water temperature favorability.

    Rules:
        <20°C → 0; 20–25°C → 1; >25°C → 2.
    """
    if water_temperature_c < TEMP_COLD_MAX_C:
        return 0, None
    if water_temperature_c <= TEMP_WARM_MAX_C:
        return 1, f"Water temperature is between {TEMP_COLD_MAX_C}°C and {TEMP_WARM_MAX_C}°C"
    return 2, f"Water temperature exceeds {TEMP_WARM_MAX_C}°C"


def score_phosphorus(phosphorus_ug_l: float) -> tuple[int, Optional[str]]:
    """
    Score dissolved phosphorus favorability (µg/L).

    Rules:
        <20 → 0; 20–50 → 1; >50 → 2.
    """
    if phosphorus_ug_l < PHOSPHORUS_LOW_MAX_UG_L:
        return 0, None
    if phosphorus_ug_l <= PHOSPHORUS_MODERATE_MAX_UG_L:
        return (
            1,
            f"Phosphorus is between {PHOSPHORUS_LOW_MAX_UG_L} and "
            f"{PHOSPHORUS_MODERATE_MAX_UG_L} µg/L",
        )
    return 2, f"Phosphorus exceeds {PHOSPHORUS_MODERATE_MAX_UG_L} µg/L"


def score_nitrogen(nitrogen_mg_l: float) -> tuple[int, Optional[str]]:
    """
    Score nitrogen favorability (mg/L).

    Rules:
        <0.5 → 0; 0.5–1.0 → 1; >1.0 → 2.
    """
    if nitrogen_mg_l < NITROGEN_LOW_MAX_MG_L:
        return 0, None
    if nitrogen_mg_l <= NITROGEN_MODERATE_MAX_MG_L:
        return (
            1,
            f"Nitrogen is between {NITROGEN_LOW_MAX_MG_L} and "
            f"{NITROGEN_MODERATE_MAX_MG_L} mg/L",
        )
    return 2, f"Nitrogen exceeds {NITROGEN_MODERATE_MAX_MG_L} mg/L"


def score_streamflow(
    streamflow_cfs: float,
    seasonal_median_streamflow_cfs: float,
) -> tuple[int, Optional[str]]:
    """
    Score streamflow relative to seasonal median (cfs).

    Rules:
        flow > median → 0;
        flow within ±10% of median → 1;
        flow < 90% of median → 2.

    Values above the median are scored 0 even if they fall within +10% of the median.
    """
    median = seasonal_median_streamflow_cfs
    if median <= 0:
        raise ValueError("seasonal_median_streamflow_cfs must be positive")

    low_threshold = STREAMFLOW_LOW_FRACTION_OF_MEDIAN * median
    band = STREAMFLOW_NEAR_MEDIAN_BAND * median

    if streamflow_cfs > median:
        return 0, None
    if streamflow_cfs < low_threshold:
        return 2, "Streamflow is below seasonal median"
    if abs(streamflow_cfs - median) <= band:
        return 1, "Streamflow is within ±10% of seasonal median"
    return 1, "Streamflow is reduced relative to seasonal median"


def score_rainfall(rainfall_7day_in: float) -> tuple[int, Optional[str]]:
    """
    Score recent rainfall favorability (7-day total, inches).

    Rules:
        <0.5 in → 0; 0.5–2 in → 1; >2 in → 2.
    """
    if rainfall_7day_in < RAINFALL_DRY_MAX_IN:
        return 0, None
    if rainfall_7day_in <= RAINFALL_MODERATE_MAX_IN:
        return (
            1,
            f"Rainfall in the past 7 days is between {RAINFALL_DRY_MAX_IN} and "
            f"{RAINFALL_MODERATE_MAX_IN} inches",
        )
    return 2, "Recent runoff event detected"


def score_solar_radiation(solar_radiation_level: str) -> tuple[int, Optional[str]]:
    """
    Score sunlight favorability.

    Rules:
        low → 0; moderate → 1; high → 2.
    """
    level = solar_radiation_level.strip().lower()
    if level not in SOLAR_RADIATION_LEVELS:
        raise ValueError(
            f"solar_radiation_level must be one of {sorted(SOLAR_RADIATION_LEVELS)!r}, "
            f"got {solar_radiation_level!r}"
        )
    if level == "low":
        return 0, None
    if level == "moderate":
        return 1, "Solar radiation is moderate"
    return 2, "Solar radiation is high"


def classify_favorability(score: int, max_possible_score: int) -> FavorabilityClassification:
    """
    Map score to a favorability tier using proportional breakpoints.

    When all six factors are present (max 12), this matches the published bands:
    0–3 LOW, 4–7 MODERATE, 8–10 HIGH, 11–12 VERY HIGH.
    """
    if max_possible_score <= 0:
        return FavorabilityClassification.LOW

    ratio = score / max_possible_score
    low_cut = CLASSIFICATION_LOW_MAX_SCORE / (FACTOR_COUNT * MAX_POINTS_PER_FACTOR)
    moderate_cut = CLASSIFICATION_MODERATE_MAX_SCORE / (
        FACTOR_COUNT * MAX_POINTS_PER_FACTOR
    )
    high_cut = CLASSIFICATION_HIGH_MAX_SCORE / (FACTOR_COUNT * MAX_POINTS_PER_FACTOR)

    if ratio <= low_cut:
        return FavorabilityClassification.LOW
    if ratio <= moderate_cut:
        return FavorabilityClassification.MODERATE
    if ratio <= high_cut:
        return FavorabilityClassification.HIGH
    return FavorabilityClassification.VERY_HIGH


@dataclass(frozen=True)
class _RegisteredFactor:
    bfi_key: str
    value: Any
    evaluate: Callable[[], tuple[int, Optional[str]]]


class ScoringEngine(Protocol):
    """Protocol for pluggable scoring backends (rules today, ML later)."""

    def calculate(
        self,
        *,
        water_temperature_c: Optional[float] = None,
        phosphorus_ug_l: Optional[float] = None,
        nitrogen_mg_l: Optional[float] = None,
        streamflow_cfs: Optional[float] = None,
        seasonal_median_streamflow_cfs: Optional[float] = None,
        rainfall_7day_in: Optional[float] = None,
        solar_radiation_level: Optional[str] = None,
    ) -> BloomFavorabilityResult:
        ...


class RuleBasedScoringEngine:
    """
    Transparent rule-based BFI scorer.

    Missing inputs exclude that factor from the total and from ``max_possible_score``.
    Streamflow requires both flow and seasonal median; if either is missing, streamflow
    is excluded entirely.
    """

    def calculate(
        self,
        *,
        water_temperature_c: Optional[float] = None,
        phosphorus_ug_l: Optional[float] = None,
        nitrogen_mg_l: Optional[float] = None,
        streamflow_cfs: Optional[float] = None,
        seasonal_median_streamflow_cfs: Optional[float] = None,
        rainfall_7day_in: Optional[float] = None,
        solar_radiation_level: Optional[str] = None,
    ) -> BloomFavorabilityResult:
        registered = self._register_factors(
            water_temperature_c=water_temperature_c,
            phosphorus_ug_l=phosphorus_ug_l,
            nitrogen_mg_l=nitrogen_mg_l,
            streamflow_cfs=streamflow_cfs,
            seasonal_median_streamflow_cfs=seasonal_median_streamflow_cfs,
            rainfall_7day_in=rainfall_7day_in,
            solar_radiation_level=solar_radiation_level,
        )

        factor_rows: list[dict[str, Any]] = []
        reasons: list[str] = []
        total = 0
        max_possible = len(registered) * MAX_POINTS_PER_FACTOR

        for item in registered:
            points, reason = item.evaluate()
            total += points
            if reason:
                reasons.append(reason)
            row = {
                **factor_metadata(item.bfi_key),
                "value": item.value,
                "points": points,
                "status": _status_for_points(points),
            }
            factor_rows.append(row)

        favorability_percent = (
            round((total / max_possible) * 100.0, 2) if max_possible else 0.0
        )
        classification = classify_favorability(total, max_possible)

        return BloomFavorabilityResult(
            score=total,
            max_possible_score=max_possible,
            favorability_percent=favorability_percent,
            classification=classification.value,
            factors=factor_rows,
            reasons=reasons,
        )

    def _register_factors(
        self,
        *,
        water_temperature_c: Optional[float],
        phosphorus_ug_l: Optional[float],
        nitrogen_mg_l: Optional[float],
        streamflow_cfs: Optional[float],
        seasonal_median_streamflow_cfs: Optional[float],
        rainfall_7day_in: Optional[float],
        solar_radiation_level: Optional[str],
    ) -> Sequence[_RegisteredFactor]:
        factors: list[_RegisteredFactor] = []

        if not _is_missing(water_temperature_c):
            temp = float(water_temperature_c)  # type: ignore[arg-type]
            factors.append(
                _RegisteredFactor(
                    bfi_key="water_temperature_c",
                    value=temp,
                    evaluate=lambda t=temp: score_water_temperature(t),
                )
            )

        if not _is_missing(phosphorus_ug_l):
            p = float(phosphorus_ug_l)  # type: ignore[arg-type]
            factors.append(
                _RegisteredFactor(
                    bfi_key="phosphorus_ug_l",
                    value=p,
                    evaluate=lambda ph=p: score_phosphorus(ph),
                )
            )

        if not _is_missing(nitrogen_mg_l):
            n = float(nitrogen_mg_l)  # type: ignore[arg-type]
            factors.append(
                _RegisteredFactor(
                    bfi_key="nitrogen_mg_l",
                    value=n,
                    evaluate=lambda ni=n: score_nitrogen(ni),
                )
            )

        streamflow_available = not _is_missing(streamflow_cfs) and not _is_missing(
            seasonal_median_streamflow_cfs
        )
        if streamflow_available:
            flow = float(streamflow_cfs)  # type: ignore[arg-type]
            median = float(seasonal_median_streamflow_cfs)  # type: ignore[arg-type]
            factors.append(
                _RegisteredFactor(
                    bfi_key="streamflow_cfs",
                    value={"discharge_cfs": flow, "seasonal_median_cfs": median},
                    evaluate=lambda f=flow, m=median: score_streamflow(f, m),
                )
            )

        if not _is_missing(rainfall_7day_in):
            rain = float(rainfall_7day_in)  # type: ignore[arg-type]
            factors.append(
                _RegisteredFactor(
                    bfi_key="rainfall_7day_in",
                    value=rain,
                    evaluate=lambda r=rain: score_rainfall(r),
                )
            )

        if not _is_missing(solar_radiation_level):
            solar = str(solar_radiation_level)
            factors.append(
                _RegisteredFactor(
                    bfi_key="solar_radiation_level",
                    value=solar.strip().lower(),
                    evaluate=lambda s=solar: score_solar_radiation(s),
                )
            )

        return factors


_default_engine: ScoringEngine = RuleBasedScoringEngine()


def set_scoring_engine(engine: ScoringEngine) -> None:
    """Replace the module-level scoring engine (e.g. with an ML-backed implementation)."""
    global _default_engine
    _default_engine = engine


def get_scoring_engine() -> ScoringEngine:
    """Return the active scoring engine."""
    return _default_engine


def calculate_bloom_favorability(
    *,
    water_temperature_c: Optional[float] = None,
    phosphorus_ug_l: Optional[float] = None,
    orthophosphate_mg_l_as_p: Optional[float] = None,
    total_phosphorus_mg_l_as_p: Optional[float] = None,
    nitrogen_mg_l: Optional[float] = None,
    nitrate_nitrite_mg_l_as_n: Optional[float] = None,
    ammonia_mg_l_as_n: Optional[float] = None,
    streamflow_cfs: Optional[float] = None,
    seasonal_median_streamflow_cfs: Optional[float] = None,
    rainfall_7day_in: Optional[float] = None,
    solar_radiation_level: Optional[str] = None,
    as_dict: bool = True,
) -> dict[str, Any] | BloomFavorabilityResult:
    """
    Compute the Bloom Favorability Index from environmental observations.

    Parameters mirror expected NOAA/USGS/water-quality feed fields. Any parameter
    left ``None`` (or blank for solar level) is omitted from scoring; the maximum
    possible score is reduced accordingly.

    Args:
        water_temperature_c: Water temperature in degrees Celsius.
        phosphorus_ug_l: Dissolved phosphorus in µg/L (BFI rules).
        orthophosphate_mg_l_as_p: USGS 00671 orthophosphate (mg/L as P); converted to µg/L.
        total_phosphorus_mg_l_as_p: USGS 00665 total P (mg/L as P); converted to µg/L.
        nitrogen_mg_l: Nitrogen in mg/L as N for BFI rules.
        nitrate_nitrite_mg_l_as_n: USGS 00631 (mg/L as N).
        ammonia_mg_l_as_n: USGS 00608 (mg/L as N); summed with nitrate+nitrite when used.
        streamflow_cfs: Instantaneous or daily mean streamflow (cfs).
        seasonal_median_streamflow_cfs: Baseline median flow for the season (cfs).
        rainfall_7day_in: Total rainfall over the prior 7 days (inches).
        solar_radiation_level: ``"low"``, ``"moderate"``, or ``"high"``.
        as_dict: If True (default), return a JSON-ready dict; otherwise the result object.

    Returns:
        BFI payload with ``score``, ``max_possible_score``, ``favorability_percent``,
        ``classification``, ``factors``, and ``reasons``.

    Example:
        >>> result = calculate_bloom_favorability(
        ...     water_temperature_c=27,
        ...     phosphorus_ug_l=75,
        ...     nitrogen_mg_l=1.2,
        ...     streamflow_cfs=80,
        ...     seasonal_median_streamflow_cfs=150,
        ...     rainfall_7day_in=2.5,
        ...     solar_radiation_level="high",
        ... )
        >>> result["classification"]
        'VERY HIGH FAVORABILITY'
    """
    resolved_p = resolve_phosphorus_ug_l(
        phosphorus_ug_l=phosphorus_ug_l,
        orthophosphate_mg_l_as_p=orthophosphate_mg_l_as_p,
        total_phosphorus_mg_l_as_p=total_phosphorus_mg_l_as_p,
    )
    resolved_n = resolve_nitrogen_mg_l(
        nitrogen_mg_l=nitrogen_mg_l,
        nitrate_nitrite_mg_l_as_n=nitrate_nitrite_mg_l_as_n,
        ammonia_mg_l_as_n=ammonia_mg_l_as_n,
    )
    result = _default_engine.calculate(
        water_temperature_c=water_temperature_c,
        phosphorus_ug_l=resolved_p,
        nitrogen_mg_l=resolved_n,
        streamflow_cfs=streamflow_cfs,
        seasonal_median_streamflow_cfs=seasonal_median_streamflow_cfs,
        rainfall_7day_in=rainfall_7day_in,
        solar_radiation_level=solar_radiation_level,
    )
    if as_dict:
        return result.to_dict()
    return result


def calculate_bloom_favorability_from_observations(
    observations: Sequence[Mapping[str, Any]],
    *,
    as_of_date: str,
    water_temperature_c: Optional[float] = None,
    phosphorus_ug_l: Optional[float] = None,
    orthophosphate_mg_l_as_p: Optional[float] = None,
    total_phosphorus_mg_l_as_p: Optional[float] = None,
    nitrogen_mg_l: Optional[float] = None,
    nitrate_nitrite_mg_l_as_n: Optional[float] = None,
    ammonia_mg_l_as_n: Optional[float] = None,
    seasonal_median_streamflow_cfs: Optional[float] = None,
    solar_radiation_level: Optional[str] = None,
    as_dict: bool = True,
) -> dict[str, Any] | BloomFavorabilityResult:
    """
    Build BFI inputs from Foxwatch ``Observation`` records plus optional overrides.

    Maps client metrics to manifest attributes:

    - ``metric='discharge'`` / USGS ``00060`` → ``streamflow_cfs`` (ft³/s)
    - ``metric='precipitation'`` → 7-day sum converted to inches when unit is mm

    Explicit keyword arguments override values inferred from ``observations``.
    """
    streamflow_cfs = None
    for obs in observations:
        if obs.get("metric") == "discharge" and obs.get("observation_date") == as_of_date:
            if obs.get("value") is not None:
                streamflow_cfs = float(obs["value"])
            break

    rainfall_7day_in = sum_precipitation_7day_in(
        list(observations), end_date=as_of_date, metric="precipitation"
    )

    return calculate_bloom_favorability(
        water_temperature_c=water_temperature_c,
        phosphorus_ug_l=phosphorus_ug_l,
        orthophosphate_mg_l_as_p=orthophosphate_mg_l_as_p,
        total_phosphorus_mg_l_as_p=total_phosphorus_mg_l_as_p,
        nitrogen_mg_l=nitrogen_mg_l,
        nitrate_nitrite_mg_l_as_n=nitrate_nitrite_mg_l_as_n,
        ammonia_mg_l_as_n=ammonia_mg_l_as_n,
        streamflow_cfs=streamflow_cfs,
        seasonal_median_streamflow_cfs=seasonal_median_streamflow_cfs,
        rainfall_7day_in=rainfall_7day_in,
        solar_radiation_level=solar_radiation_level,
        as_dict=as_dict,
    )
