import json
from datetime import date
from pathlib import Path

from weather_risk.data.sources import parse_nri_features, parse_open_meteo

FIXTURES = Path(__file__).parents[1] / "fixtures"


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_open_meteo_parses_days_and_keeps_nulls():
    ds = parse_open_meteo("denver", _load("open_meteo_sample.json"), retrieved_at="2026-11-13")
    assert ds.hub_id == "denver"
    assert ds.start_date == date(2025, 1, 1) and ds.end_date == date(2025, 1, 5)
    assert len(ds.days) == 5
    assert ds.days[1].snowfall_cm == 6.3
    assert ds.days[1].tmin_c == -19.2
    assert ds.days[2].gust_max_kmh == 92.5
    assert ds.days[3].snowfall_cm is None


def test_nri_parses_counties_keeps_nulls_and_uses_ifld():
    counties, version = parse_nri_features(_load("nri_page_sample.json")["features"])
    assert version == "December 2025"
    by_fips = {c.fips: c for c in counties}
    assert by_fips["08031"].afreq["HRCN"] is None
    assert by_fips["12086"].afreq["IFLD"] == 4
    assert by_fips["48113"].afreq["HWAV"] > 19
    assert "RFLD" not in by_fips["48113"].afreq
    assert by_fips["12086"].county == "Miami-Dade" and by_fips["12086"].state == "FL"
