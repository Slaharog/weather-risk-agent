from datetime import date, timedelta

import pytest

from weather_risk.data.models import DailyWeather, NriCounty
from weather_risk.scoring.engine import (
    HAZARD_WEIGHTS,
    Hazard,
    IndicatorValue,
    combine,
    indicator_values,
    overall_score,
)


def test_weights_match_the_documented_table_exactly():
    assert HAZARD_WEIGHTS == {
        Hazard.WINTER: {"fema_WNTW": 0.25, "fema_ISTM": 0.15, "fema_CWAV": 0.10,
                        "heavy_snow_days": 0.25, "severe_cold_days": 0.25},
        Hazard.HEAT: {"fema_HWAV": 0.50, "extreme_heat_days": 0.50},
        Hazard.FLOOD: {"fema_flood": 0.70, "heavy_rain_days": 0.30},
        Hazard.HURRICANE: {"fema_HRCN": 1.00},
        Hazard.SEVERE_STORMS: {"fema_TRND": 0.30, "fema_HAIL": 0.25, "fema_SWND": 0.25,
                               "high_wind_days": 0.20},
    }
    for weights in HAZARD_WEIGHTS.values():
        assert sum(weights.values()) == pytest.approx(1.0)


def _iv(score, raw=1.0):
    return IndicatorValue(score=score, raw_value=raw, raw_unit="events/yr", source="test")


def test_contributions_add_up_to_the_hazard_score():
    values = {"fema_HWAV": _iv(90.0), "extreme_heat_days": _iv(40.0)}
    hs = combine("dallas", Hazard.HEAT, values)
    assert hs.score == pytest.approx(65.0)
    assert sum(c.contribution for c in hs.components) == pytest.approx(hs.score)
    assert hs.missing == []


def test_missing_indicator_renormalizes_remaining_weights_and_is_flagged():
    values = {"fema_WNTW": _iv(80.0), "fema_ISTM": _iv(40.0), "fema_CWAV": _iv(20.0),
              "heavy_snow_days": None, "severe_cold_days": None}
    hs = combine("denver", Hazard.WINTER, values)
    # remaining weights 0.25, 0.15, 0.10 -> normalized 0.5, 0.3, 0.2
    assert hs.score == pytest.approx(0.5 * 80 + 0.3 * 40 + 0.2 * 20)
    assert sorted(hs.missing) == ["heavy_snow_days", "severe_cold_days"]
    assert sum(c.contribution for c in hs.components) == pytest.approx(hs.score)


def test_overall_is_the_mean_of_the_five_hazards():
    hazards = {h: combine("x", h, {k: _iv(s) for k in HAZARD_WEIGHTS[h]})
               for h, s in zip(Hazard, [10.0, 20.0, 30.0, 40.0, 50.0], strict=True)}
    assert overall_score("x", hazards).score == pytest.approx(30.0)


def _county(fips, **afreq):
    codes = ("HRCN", "IFLD", "CFLD", "WNTW", "ISTM", "CWAV", "HWAV", "TRND", "HAIL", "SWND")
    return NriCounty(fips=fips, county=fips, state="XX", afreq={c: afreq.get(c) for c in codes})


def test_flood_uses_the_worse_of_inland_and_coastal_flooding():
    hub_county = _county("A", IFLD=1.0, CFLD=3.0)
    others = [_county(f"X{i}", IFLD=4.0, CFLD=4.0) for i in range(99)]
    population = [hub_county, *others]  # p99 = 4.0 for both flood types
    days = [DailyWeather(date=date(2020, 1, 1) + timedelta(days=i), snowfall_cm=0,
                         precipitation_mm=0, tmax_c=20, tmin_c=10, gust_max_kmh=10)
            for i in range(366)]
    values = indicator_values(hub_county, population, days)
    # inland 1.0 / 4.0 = 25; coastal 3.0 / 4.0 = 75 -> coastal wins
    assert values["fema_flood"].score == pytest.approx(75.0)
    assert "coastal" in values["fema_flood"].label.lower()


def test_engine_reports_a_hub_whose_county_is_missing_from_the_snapshot():
    from weather_risk.data.models import NriDataset, WeatherDataset
    from weather_risk.data.store import Snapshot
    from weather_risk.hubs import load_hubs
    from weather_risk.scoring.engine import DataError, Engine

    hub = load_hubs()[0]
    snap = Snapshot(weather={hub.id: WeatherDataset(hub_id=hub.id, start_date=date(2020, 1, 1),
                                                     end_date=date(2020, 1, 1), retrieved_at="x",
                                                     days=[])},
                    nri=NriDataset(version="v", retrieved_at="x", counties=[]))
    with pytest.raises(DataError, match=hub.county_fips):
        Engine([hub], snap)
