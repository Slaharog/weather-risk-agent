"""fetch_all: shared by `wra refresh` and the alert check (spec 002, FR-202). No network."""

import pytest

from weather_risk.data import refresh, store


def test_failed_source_is_reported_and_refresh_still_completes(tmp_path, monkeypatch):
    def broken_weather(hub):
        raise ConnectionError("down")

    def broken_nri():
        raise TimeoutError("slow")

    monkeypatch.setattr(refresh.sources, "fetch_weather", broken_weather)
    monkeypatch.setattr(refresh.sources, "fetch_nri", broken_nri)
    lines = []
    result = refresh.fetch_all(tmp_path, "all", echo=lines.append, pause=lambda s: None)

    assert len(result.failures) == 17  # 16 hubs + NRI
    assert result.failures[0].startswith("weather:") and result.failures[-1] == "nri"
    assert all("previous data kept" in line for line in lines)
    assert (tmp_path / store.COMPLETE_MARKER).exists()  # the server reloads only after this


def test_unknown_source_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        refresh.fetch_all(tmp_path, "everything")
