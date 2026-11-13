from datetime import date

import pytest

from weather_risk.data.models import DailyWeather
from weather_risk.scoring.stats import STATS, compute_stat


def _day(d, snow=0.0, rain=0.0, tmax=20.0, tmin=10.0, gust=20.0):
    return DailyWeather(date=d, snowfall_cm=snow, precipitation_mm=rain, tmax_c=tmax,
                        tmin_c=tmin, gust_max_kmh=gust)


def _year(overrides=None):
    """365 days of 2025; overrides map day-of-year (1-based) -> field values."""
    days = []
    for i in range(365):
        d = date.fromordinal(date(2025, 1, 1).toordinal() + i)
        days.append(_day(d, **(overrides or {}).get(i + 1, {})))
    return days


def test_all_eight_stats_exist():
    assert set(STATS) == {
        "snowfall_days_pct", "heavy_snow_days", "extreme_heat_days", "severe_cold_days",
        "heavy_rain_days", "high_wind_days", "total_snowfall_cm", "total_precipitation_mm",
    }


def test_snowfall_days_pct_uses_the_measurable_snow_threshold():
    days = _year({1: {"snow": 0.25}, 2: {"snow": 0.24}, 3: {"snow": 3.0}})
    s = compute_stat("denver", days, "snowfall_days_pct", 2025)
    assert s.qualifying_days == 2  # 0.25 and 3.0 count; 0.24 does not
    assert s.days_with_data == 365 and s.missing_days == 0
    assert s.value == pytest.approx(100 * 2 / 365)
    assert "0.25 cm" in s.definition
    assert (s.period_start, s.period_end) == (date(2025, 1, 1), date(2025, 12, 31))


def test_missing_days_are_excluded_from_the_denominator_and_reported():
    days = _year({1: {"snow": 1.0}})
    days[10] = DailyWeather(date=days[10].date, snowfall_cm=None, precipitation_mm=0.0,
                            tmax_c=1.0, tmin_c=0.0, gust_max_kmh=1.0)
    s = compute_stat("denver", days, "snowfall_days_pct", 2025)
    assert s.days_with_data == 364 and s.missing_days == 1
    assert s.value == pytest.approx(100 / 364)


def test_count_and_total_stats():
    days = _year({1: {"tmax": 36.0}, 2: {"tmax": 35.0}, 3: {"rain": 60.0, "snow": 5.5}})
    assert compute_stat("x", days, "extreme_heat_days", 2025).value == 2
    assert compute_stat("x", days, "heavy_rain_days", 2025).value == 1
    assert compute_stat("x", days, "total_snowfall_cm", 2025).value == pytest.approx(5.5)
    assert compute_stat("x", days, "total_precipitation_mm", 2025).value == pytest.approx(60.0)


def test_only_the_requested_year_is_used():
    days = _year({1: {"snow": 1.0}}) + [_day(date(2024, 12, 31), snow=9.0)]
    assert compute_stat("x", days, "snowfall_days_pct", 2025).qualifying_days == 1


@pytest.mark.parametrize("year", [2015, 2026])
def test_year_outside_the_covered_period_is_rejected(year):
    with pytest.raises(ValueError):
        compute_stat("x", _year(), "snowfall_days_pct", year)


def test_unknown_stat_is_rejected():
    with pytest.raises(ValueError):
        compute_stat("x", _year(), "earthquakes", 2025)


def test_year_without_any_usable_data_is_an_error_not_zero():
    days = [DailyWeather(date=d.date, snowfall_cm=None, precipitation_mm=0.0, tmax_c=1.0,
                         tmin_c=0.0, gust_max_kmh=1.0) for d in _year()]
    with pytest.raises(ValueError, match="no data"):
        compute_stat("x", days, "snowfall_days_pct", 2025)


def test_days_absent_from_the_dataset_count_as_missing():
    days = _year()[:300]  # 65 days of 2025 not in the data at all
    s = compute_stat("x", days, "snowfall_days_pct", 2025)
    assert s.days_with_data == 300 and s.missing_days == 65
