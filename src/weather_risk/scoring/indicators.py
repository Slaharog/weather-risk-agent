"""Indicators: the 0-100 building blocks of every hazard score (data-model.md section 3).

Two kinds, both on fixed national yardsticks so a hub's score never depends on which
other hubs are in the list:

1. FEMA frequency percentile: how the hub county's expected events per year compare
   with all ~3,232 US counties.
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


def fema_percentile(value: float | None, population: Sequence[float | None]) -> float:
    """National percentile of a county's annualized frequency.

    0 when FEMA rates the hazard as absent (0) or not applicable (null). Otherwise the share
    of all counties whose frequency is at or below this one, with null counted as 0.
    """
    if not value:
        return 0.0
    at_or_below = sum(1 for v in population if (v or 0.0) <= value)
    return 100.0 * at_or_below / len(population)


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
