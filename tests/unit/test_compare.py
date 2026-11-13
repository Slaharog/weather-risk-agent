import pytest

from weather_risk.scoring.engine import Engine, UnknownHub, verdict


@pytest.fixture(scope="module")
def engine():
    return Engine.from_settings()


def test_matrix_holds_every_hub_and_hazard_with_components(engine):
    c = engine.compare_hubs(["miami", "houston"], ["hurricane", "flood"])
    assert [r.hub_id for r in c.rows] == ["miami", "houston"]
    for row in c.rows:
        assert set(row.scores) == {"hurricane", "flood"}
        for metric, cell in row.scores.items():
            assert cell.score == pytest.approx(engine.metric_score(row.hub_id, metric))
            assert cell.components  # explanation material for each cell


def test_most_exposed_is_the_higher_score(engine):
    c = engine.compare_hubs(["miami", "houston"], ["hurricane", "flood"])
    for metric in ("hurricane", "flood"):
        best = max(c.rows, key=lambda r: r.scores[metric].score).hub_id
        assert c.most_exposed[metric] == best


def test_equal_scores_are_reported_as_a_tie():
    assert verdict({"a": 10.0, "b": 10.0}) == "tie"
    assert verdict({"a": 10.0, "b": 12.0}) == "b"


@pytest.mark.parametrize("hubs, metrics", [
    (["miami"], ["flood"]),                       # fewer than 2 hubs
    (["miami", "miami"], ["flood"]),              # duplicates
    (["miami", "houston"], []),                   # no hazards
    ([f"h{i}" for i in range(7)], ["flood"]),     # more than 6 hubs
    (["miami", "houston"], ["flood", "flood"]),   # duplicate hazards
    (["miami", "houston"], ["earthquake"]),       # unknown hazard
])
def test_argument_limits(engine, hubs, metrics):
    with pytest.raises((ValueError, UnknownHub)):
        engine.compare_hubs(hubs, metrics)


def test_unknown_hub_raises(engine):
    with pytest.raises(UnknownHub):
        engine.compare_hubs(["miami", "boston"], ["flood"])
