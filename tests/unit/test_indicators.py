from datetime import date, timedelta

import pytest

from weather_risk.data.models import DailyWeather
from weather_risk.scoring.indicators import (
    OBSERVED_INDICATORS,
    annual_rate,
    fema_ratio,
    national_p99,
    observed_score,
    qualifies,
)


def _day(i=0, snow=0.0, rain=0.0, tmax=20.0, tmin=10.0, gust=20.0):
    return DailyWeather(date=date(2020, 1, 1) + timedelta(days=i), snowfall_cm=snow,
                        precipitation_mm=rain, tmax_c=tmax, tmin_c=tmin, gust_max_kmh=gust)


# ---------- FEMA frequency ratio to the national 99th-percentile county (data-model 3a) ----------

POPULATION = [None] + [float(i) for i in range(101)]  # null, 0, 1, ..., 100


def test_national_p99_counts_null_as_zero():
    # sorted with null as 0: [0, 0, 1, ..., 100]; index floor(0.99 * 101) = 99 -> value 98
    assert national_p99(POPULATION) == 98.0


def test_ratio_is_zero_when_hazard_absent_or_not_applicable():
    assert fema_ratio(None, p99=98.0) == 0
    assert fema_ratio(0.0, p99=98.0) == 0


def test_ratio_is_linear_up_to_the_p99_county_and_capped_at_100():
    assert fema_ratio(49.0, p99=98.0) == pytest.approx(50.0)
    assert fema_ratio(98.0, p99=98.0) == pytest.approx(100.0)
    assert fema_ratio(150.0, p99=98.0) == 100


def test_ratio_is_zero_when_no_county_has_the_hazard():
    assert fema_ratio(1.0, p99=0.0) == 0


# ---------- Observed weather indicators (data-model 3b) ----------

def test_thresholds_and_caps_are_exactly_as_documented():
    expected = {
        "heavy_snow_days": (5.0, 15),
        "severe_cold_days": (-18.0, 20),
        "extreme_heat_days": (35.0, 60),
        "heavy_rain_days": (50.0, 4),
        "high_wind_days": (90.0, 10),
    }
    assert {k: (v.threshold, v.cap) for k, v in OBSERVED_INDICATORS.items()} == expected


@pytest.mark.parametrize("name, day, expected", [
    ("heavy_snow_days", _day(snow=5.0), True),
    ("heavy_snow_days", _day(snow=4.9), False),
    ("severe_cold_days", _day(tmin=-18.0), True),
    ("severe_cold_days", _day(tmin=-17.9), False),
    ("extreme_heat_days", _day(tmax=35.0), True),
    ("extreme_heat_days", _day(tmax=34.9), False),
    ("heavy_rain_days", _day(rain=50.0), True),
    ("heavy_rain_days", _day(rain=49.9), False),
    ("high_wind_days", _day(gust=90.0), True),
    ("high_wind_days", _day(gust=89.9), False),
])
def test_threshold_boundaries_are_inclusive(name, day, expected):
    assert qualifies(day, OBSERVED_INDICATORS[name]) is expected


def test_missing_value_is_neither_qualifying_nor_counted():
    day = DailyWeather(date=date(2020, 1, 1), snowfall_cm=None, precipitation_mm=0.0,
                       tmax_c=1.0, tmin_c=-1.0, gust_max_kmh=1.0)
    assert qualifies(day, OBSERVED_INDICATORS["heavy_snow_days"]) is None


def test_annual_rate_excludes_missing_days_and_scales_to_a_year():
    # 4 years of days with data; 8 qualifying days -> 2 per year. One extra day is missing.
    n = round(4 * 365.25)
    days = [_day(i, snow=6.0 if i < 8 else 0.0) for i in range(n)]
    days.append(DailyWeather(date=date(2030, 1, 1), snowfall_cm=None, precipitation_mm=0.0,
                             tmax_c=0.0, tmin_c=0.0, gust_max_kmh=0.0))
    rate, days_with_data = annual_rate(days, OBSERVED_INDICATORS["heavy_snow_days"])
    assert days_with_data == n
    assert rate == pytest.approx(2.0, abs=0.01)


def test_observed_score_maps_linearly_and_clamps_at_cap():
    assert observed_score(30, cap=60) == pytest.approx(50.0)
    assert observed_score(0, cap=60) == 0
    assert observed_score(120, cap=60) == 100
