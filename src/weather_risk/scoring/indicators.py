"""Indicators: the 0-100 building blocks of every hazard score (data-model.md section 3).

Two kinds, both on fixed national yardsticks so a hub's score never depends on which
other hubs are in the list:

1. FEMA frequency ratio: the hub county's expected events per year as a share of the
   99th-percentile US county (all ~3,232 counties), capped at 100.
2. Observed weather indicator: qualifying days per year at the hub (Open-Meteo, 2016-2025),
   mapped onto 0-100 with a fixed cap. The thresholds and caps are documented judgment calls.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from operator import ge, le

from weather_risk.data.models import DailyWeather

DAYS_PER_YEAR = 365.25


@dataclass(frozen=True)
class ObservedIndicator:
    name: str
    field: str  # attribute of DailyWeather
    compare: str  # ">=" or "<="
    threshold: float
    cap: float  # qualifying days per year that map to a score of 100
    description: str


OBSERVED_INDICATORS: dict[str, ObservedIndicator] = {
    i.name: i
    for i in [
        ObservedIndicator("heavy_snow_days", "snowfall_cm", ">=", 5.0, 15,
                          "days with snowfall >= 5 cm (about 2 in)"),
        ObservedIndicator("severe_cold_days", "tmin_c", "<=", -18.0, 20,
                          "days with minimum temperature <= -18 °C (0 °F)"),
        ObservedIndicator("extreme_heat_days", "tmax_c", ">=", 35.0, 60,
                          "days with maximum temperature >= 35 °C (95 °F)"),
        ObservedIndicator("heavy_rain_days", "precipitation_mm", ">=", 50.0, 4,
                          "days with precipitation >= 50 mm (about 2 in)"),
        ObservedIndicator("high_wind_days", "gust_max_kmh", ">=", 90.0, 10,
                          "days with maximum wind gust >= 90 km/h (about 56 mph)"),
    ]
}

_OPS = {">=": ge, "<=": le}


def national_p99(population: Sequence[float | None]) -> float:
    """Annualized frequency of the 99th-percentile US county (null counted as 0).

    This is the fixed national yardstick for a FEMA hazard: a county this exposed or more
    scores 100. Using p99 instead of the maximum keeps one extreme county from squashing
    every other score.
    """
    values = sorted(v or 0.0 for v in population)
    return values[int(0.99 * (len(values) - 1))]


def fema_ratio(value: float | None, p99: float) -> float:
    """FEMA indicator: 100 x county frequency / p99 frequency, capped at 100.

    Linear, so magnitude is kept: a county with 1/26 of Miami's hurricane frequency gets
    about 1/26 of its score. (A percentile rank was tried first and rejected: it made rare
    hazards look large; see docs/decisions.md, 2026-11-13.)
    0 when FEMA rates the hazard as absent (0) or not applicable (null).
    """
    if not value or p99 <= 0:
        return 0.0
    return min(100.0, 100.0 * value / p99)


def qualifies(day: DailyWeather, indicator: ObservedIndicator) -> bool | None:
    """True/False for a day with data; None when the needed value is missing."""
    value = getattr(day, indicator.field)
    if value is None:
        return None
    return _OPS[indicator.compare](value, indicator.threshold)


def annual_rate(days: Sequence[DailyWeather], indicator: ObservedIndicator) -> tuple[float, int]:
    """Qualifying days per year, from days with data only. Returns (rate, days_with_data)."""
    results = [qualifies(d, indicator) for d in days]
    with_data = [r for r in results if r is not None]
    if not with_data:
        return 0.0, 0
    return sum(with_data) * DAYS_PER_YEAR / len(with_data), len(with_data)


def observed_score(rate_per_year: float, cap: float) -> float:
    return min(100.0, 100.0 * rate_per_year / cap)
