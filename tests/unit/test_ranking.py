import pytest

from weather_risk.hubs import Region
from weather_risk.scoring.engine import Engine, order_with_ties, parse_metric


@pytest.fixture(scope="module")
def engine():
    return Engine.from_settings()


def test_sorted_by_unrounded_score_with_alphabetical_tie_break():
    rows = order_with_ties([("b", 50.0), ("a", 50.0), ("c", 70.0), ("d", 50.00001)])
    assert [hub for hub, _, _ in rows] == ["c", "d", "a", "b"]
    assert [rank for _, rank, _ in rows] == [1, 2, 3, 4]


def test_tied_flag_marks_equal_scores_only():
    rows = order_with_ties([("b", 50.0), ("a", 50.0), ("c", 70.0)])
    tied = {hub: t for hub, _, t in rows}
    assert tied == {"c": False, "a": True, "b": True}


def test_region_filter_returns_only_that_region_in_score_order(engine):
    rows = engine.rank_hubs("winter", region=Region.MIDWEST)
    assert len(rows) == 7
    assert all(engine.hubs[r.hub_id].region == Region.MIDWEST for r in rows)
    scores = [r.score for r in rows]
    assert scores == sorted(scores, reverse=True)
    assert [r.rank for r in rows] == list(range(1, 8))


def test_limit_and_its_bounds(engine):
    assert len(engine.rank_hubs("overall", limit=3)) == 3
    assert len(engine.rank_hubs("overall")) == 16
    for bad in (0, 17):
        with pytest.raises(ValueError):
            engine.rank_hubs("overall", limit=bad)


def test_top_drivers_are_the_two_largest_contributions(engine):
    row = engine.rank_hubs("heat", limit=1)[0]
    components = engine.scores[row.hub_id].hazards["heat"].components
    expected = sorted(components, key=lambda c: -c.contribution)[:2]
    assert [d.indicator for d in row.top_drivers] == [c.indicator for c in expected]


def test_overall_drivers_are_the_two_highest_hazards(engine):
    row = engine.rank_hubs("overall", limit=1)[0]
    hazards = engine.scores[row.hub_id].hazards
    top2 = sorted(hazards, key=lambda h: -hazards[h].score)[:2]
    assert [d.indicator for d in row.top_drivers] == [h.value for h in top2]


def test_metric_must_be_overall_or_a_known_hazard():
    assert parse_metric("overall") == "overall"
    assert parse_metric("severe_storms") == "severe_storms"
    with pytest.raises(ValueError):
        parse_metric("earthquake")
