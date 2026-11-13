"""Weather statistics for one hub and one calendar year (data-model.md section 6).

Answers factual questions such as "What percentage of days in Denver last year had
snowfall?" with the counts behind the number, so the analyst can check it.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date

from pydantic import BaseModel

from weather_risk.data.models import DailyWeather
from weather_risk.scoring.indicators import OBSERVED_INDICATORS, qualifies

FIRST_YEAR, LAST_YEAR = 2016, 2025
MEASURABLE_SNOW_CM = 0.25  # 0.1 in: the US National Weather Service "measurable snowfall"


@dataclass(frozen=True)
class StatDef:
    kind: str  # "percent", "count", or "total"
    field: str
    unit: str
    definition: str
    test: Callable[[DailyWeather], bool | None] | None = None


def _ind(name: str) -> Callable[[DailyWeather], bool | None]:
    return lambda day: qualifies(day, OBSERVED_INDICATORS[name])


def _measurable_snow(day: DailyWeather) -> bool | None:
    return None if day.snowfall_cm is None else day.snowfall_cm >= MEASURABLE_SNOW_CM


STATS: dict[str, StatDef] = {
    "snowfall_days_pct": StatDef(
        "percent", "snowfall_cm", "% of days",
        "days with snowfall >= 0.25 cm (0.1 in, the NWS 'measurable snowfall' threshold) "
        "as a share of days with data", _measurable_snow),
    "heavy_snow_days": StatDef("count", "snowfall_cm", "days",
                               OBSERVED_INDICATORS["heavy_snow_days"].description,
                               _ind("heavy_snow_days")),
    "extreme_heat_days": StatDef("count", "tmax_c", "days",
                                 OBSERVED_INDICATORS["extreme_heat_days"].description,
                                 _ind("extreme_heat_days")),
    "severe_cold_days": StatDef("count", "tmin_c", "days",
                                OBSERVED_INDICATORS["severe_cold_days"].description,
                                _ind("severe_cold_days")),
    "heavy_rain_days": StatDef("count", "precipitation_mm", "days",
                               OBSERVED_INDICATORS["heavy_rain_days"].description,
                               _ind("heavy_rain_days")),
    "high_wind_days": StatDef("count", "gust_max_kmh", "days",
                              OBSERVED_INDICATORS["high_wind_days"].description,
                              _ind("high_wind_days")),
    "total_snowfall_cm": StatDef("total", "snowfall_cm", "cm", "sum of daily snowfall"),
    "total_precipitation_mm": StatDef("total", "precipitation_mm", "mm",
                                      "sum of daily precipitation"),
}


class WeatherStat(BaseModel):
    hub_id: str
    stat: str
    period_start: date
    period_end: date
    value: float
    unit: str
    qualifying_days: int | None  # None for totals
    days_with_data: int
    missing_days: int
    definition: str


def compute_stat(hub_id: str, days: Sequence[DailyWeather], stat: str, year: int) -> WeatherStat:
    if stat not in STATS:
        raise ValueError(f"Unknown statistic '{stat}'. Use one of: {', '.join(STATS)}")
    if not FIRST_YEAR <= year <= LAST_YEAR:
        raise ValueError(f"Data covers {FIRST_YEAR}-{LAST_YEAR}; {year} is outside that period.")
    sd = STATS[stat]
    in_year = [d for d in days if d.date.year == year]
    with_data = [d for d in in_year if getattr(d, sd.field) is not None]
    missing = len(in_year) - len(with_data)

    qualifying = None
    if sd.kind == "total":
        value = sum(getattr(d, sd.field) for d in with_data)
    else:
        qualifying = sum(1 for d in with_data if sd.test(d))
        value = qualifying if sd.kind == "count" else (
            100.0 * qualifying / len(with_data) if with_data else 0.0)

    return WeatherStat(
        hub_id=hub_id, stat=stat, period_start=date(year, 1, 1), period_end=date(year, 12, 31),
        value=value, unit=sd.unit, qualifying_days=qualifying, days_with_data=len(with_data),
        missing_days=missing, definition=sd.definition,
    )
