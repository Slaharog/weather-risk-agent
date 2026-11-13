from evals.run import _args_match, grounded, numbers_in, numbers_in_json


def test_numbers_in_text_ignores_numbers_inside_words():
    assert numbers_in("Score 51.2 vs 24.4; ERA5 data; 8.2% of 365 days; -18 °C") == [
        51.2, 24.4, 8.2, 365.0, -18.0]
    assert numbers_in("1,234 events") == [1234.0]


def test_numbers_in_json_walks_values_and_strings():
    data = {"score": 46.0, "tied": False, "rows": [[1, "Dallas, TX", "heat wave +43.9"]]}
    assert sorted(numbers_in_json(data)) == [1.0, 43.9, 46.0]


def test_grounded_requires_the_exact_displayed_value():
    allowed = [51.2, 2025.0, -18.0]
    assert grounded(51.2, allowed)
    assert not grounded(18.0, allowed)  # sign flips are not accepted
    assert not grounded(51.0, allowed)  # the model rounded on its own
    assert not grounded(51.25, allowed)
    assert not grounded(0.04, [0.0])  # no tolerance around zero
    assert not grounded(95.0, allowed)


def test_args_match_subset_and_lists_as_sets():
    actual = {"hub_ids": ["houston", "miami"], "hazards": ["flood"], "extra": 1}
    assert _args_match({"hub_ids": ["miami", "houston"]}, actual)
    assert not _args_match({"hazards": ["hurricane"]}, actual)


def test_table_check_uses_the_engine_and_catches_a_wrong_number():
    import json

    from evals.run import table_mismatches
    from weather_risk.agent.tools import ToolRegistry
    from weather_risk.hubs import load_hubs
    from weather_risk.scoring.engine import Engine

    engine = Engine.from_settings()
    names = {h.name: h.id for h in load_hubs()}
    args = {"hazard": "winter", "region": "Midwest", "limit": None}
    table = ToolRegistry(engine).execute("rank_hubs", json.dumps(args)).table.model_dump()
    assert table_mismatches("rank_hubs", args, table, engine, names) == []
    table["rows"][0][3] = table["rows"][0][3] + 1.0  # tamper with one displayed score
    assert table_mismatches("rank_hubs", args, table, engine, names)
