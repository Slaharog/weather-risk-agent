"""The agent tools return the engine's numbers, rounded exactly as displayed."""

import json

import pytest

from weather_risk.agent.tools import TOOLS, ToolRegistry
from weather_risk.scoring.engine import Engine


@pytest.fixture(scope="module")
def tools():
    return ToolRegistry(Engine.from_settings())


def run(tools, name, **args):
    out = tools.execute(name, json.dumps(args))
    assert out.ok, out.result
    return out


def test_exactly_five_allowed_tools(tools):
    assert set(TOOLS) == {"list_coverage", "rank_hubs", "get_hub_breakdown", "compare_hubs",
                          "get_weather_stat"}
    assert all(s["strict"] for s in tools.specs())


def test_rank_table_matches_engine(tools):
    out = run(tools, "rank_hubs", hazard="winter", region="Midwest", limit=None)
    engine_rows = tools.engine.rank_hubs("winter", region="Midwest")
    assert [r[3] for r in out.table.rows] == [round(r.score, 1) for r in engine_rows]
    assert [d["score"] for d in out.result["data"]] == [r[3] for r in out.table.rows]


def test_breakdown_table_matches_engine(tools):
    out = run(tools, "get_hub_breakdown", hub_id="dallas")
    b = tools.engine.get_hub_breakdown("dallas")
    assert [r[1] for r in out.table.rows] == [round(h.score, 1) for h in b.hazards]


def test_compare_table_and_verdicts(tools):
    out = run(tools, "compare_hubs", hub_ids=["miami", "houston"], hazards=["hurricane", "flood"])
    assert out.table.columns == ["Hazard", "Miami, FL", "Houston, TX", "Most exposed"]
    for row in out.table.rows:
        miami, houston, verdict = row[1], row[2], row[3]
        assert verdict == ("Miami, FL" if miami > houston else "Houston, TX")


def test_stat_table_matches_engine(tools):
    out = run(tools, "get_weather_stat", hub_id="denver", stat="snowfall_days_pct", year=2025)
    s = tools.engine.weather_stat("denver", "snowfall_days_pct", 2025)
    assert out.table.rows[0][0] == round(s.value, 1)
    assert out.table.rows[0][2] == s.qualifying_days


def test_engine_errors_become_tool_errors(tools):
    out = tools.execute("get_weather_stat", json.dumps(
        {"hub_id": "denver", "stat": "snowfall_days_pct", "year": 1990}))
    assert not out.ok and "Invalid arguments" in out.result["error"]


def test_missing_flag_only_considers_the_requested_hazard(tools, monkeypatch):
    hs = tools.engine.scores["minneapolis"].hazards["winter"]
    monkeypatch.setattr(hs, "missing", ["heavy_snow_days"])
    hurricane = run(tools, "rank_hubs", hazard="hurricane", region=None, limit=None)
    winter = run(tools, "rank_hubs", hazard="winter", region=None, limit=None)
    overall = run(tools, "rank_hubs", hazard="overall", region=None, limit=None)
    assert hurricane.missing == []
    assert winter.missing == ["minneapolis: heavy_snow_days"]
    assert overall.missing == ["minneapolis: heavy_snow_days"]
