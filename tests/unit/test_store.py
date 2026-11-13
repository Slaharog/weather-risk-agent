import json
from datetime import date
from pathlib import Path

import pytest

from weather_risk.data import store
from weather_risk.data.models import DailyWeather, NriCounty, NriDataset, WeatherDataset


def _weather(hub_id: str, retrieved_at: str) -> WeatherDataset:
    day = DailyWeather(date=date(2025, 1, 1), snowfall_cm=1.0, precipitation_mm=0.0,
                       tmax_c=1.0, tmin_c=-3.0, gust_max_kmh=20.0)
    return WeatherDataset(hub_id=hub_id, start_date=day.date, end_date=day.date,
                          retrieved_at=retrieved_at, days=[day])


def _nri(version: str) -> NriDataset:
    county = NriCounty(fips="08031", county="Denver", state="CO", afreq={"HRCN": None})
    return NriDataset(version=version, retrieved_at="2026-11-13", counties=[county])


def test_failed_write_leaves_previous_file_unchanged(tmp_path: Path, monkeypatch):
    store.save_weather(tmp_path, _weather("denver", "2026-01-01"))
    target = tmp_path / "weather" / "denver.json"
    before = target.read_text(encoding="utf-8")

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(store.os, "replace", boom)
    with pytest.raises(OSError):
        store.save_weather(tmp_path, _weather("denver", "2026-11-13"))

    assert target.read_text(encoding="utf-8") == before
    assert not list((tmp_path / "weather").glob("*.tmp"))


def test_load_prefers_live_over_seed_per_source(tmp_path: Path):
    seed, live = tmp_path / "seed", tmp_path / "live"
    store.save_weather(seed, _weather("denver", "2026-01-01"))
    store.save_weather(seed, _weather("dallas", "2026-01-01"))
    store.save_nri(seed, _nri("December 2025"))
    store.save_weather(live, _weather("denver", "2026-11-13"))  # only one hub refreshed

    snap = store.load_snapshot(seed_dir=seed, data_dir=live, hub_ids=["denver", "dallas"])

    assert snap.weather["denver"].retrieved_at == "2026-11-13"
    assert snap.weather["dallas"].retrieved_at == "2026-01-01"
    assert snap.nri.version == "December 2025"


def test_manifest_records_dates_version_and_window(tmp_path: Path):
    store.save_weather(tmp_path, _weather("denver", "2026-11-13"))
    store.save_nri(tmp_path, _nri("December 2025"))
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["weather"]["denver"]["retrieved_at"] == "2026-11-13"
    assert manifest["weather"]["denver"]["start_date"] == "2025-01-01"
    assert manifest["nri"]["version"] == "December 2025"


def test_snapshot_version_changes_only_when_a_refresh_completes(tmp_path: Path):
    seed, live = tmp_path / "seed", tmp_path / "live"
    store.save_weather(live, _weather("denver", "2026-11-13"))  # mid-refresh: no marker yet
    assert store.snapshot_version(seed, live) == 0.0
    store.mark_refresh_complete(live, "2026-11-13T12:00:00")
    assert store.snapshot_version(seed, live) > 0.0
